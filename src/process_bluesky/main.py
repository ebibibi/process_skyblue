"""
Main entry point for Process BlueSky.

Runs once per invocation: checks for new BlueSky posts and cross-posts them.
Designed to be called repeatedly by an external scheduler (e.g. every 60 seconds).
"""
import sys
import os
from process_bluesky.core.config_manager import ConfigManager
from process_bluesky.core.state_manager import StateManager, CircuitBreakerTripped, DuplicateContentSkipped
from process_bluesky.core.logger import Logger
from process_bluesky.services.discord_notifier import DiscordNotifier
from process_bluesky.services.bluesky_input_service import (
    BlueskyInputService,
    BlueskyServerError,
    BlueskyRateLimitError,
    BlueskyAuthError
)
from process_bluesky.services.x_output_service import XOutputService
from process_bluesky.services.discord_log_service import DiscordLogService
from process_bluesky.utils.content_processor import ContentProcessor


def _sort_group_by_reply_chain(posts: list) -> list:
    """
    Sort a group of posts by following the reply_to chain (oldest/root first).

    Finds the post whose reply_to is not present in this group (i.e. the local
    root), then follows the chain forward.  Falls back to timestamp sort for
    any posts that cannot be chained.
    """
    group_ids = {p['id'] for p in posts}
    assigned = set()
    result = []

    # Start from the post whose reply_to is outside this group (local root)
    for start in sorted(posts, key=lambda p: p['timestamp']):
        if start['id'] in assigned:
            continue
        if start.get('reply_to') in group_ids:
            continue  # not a root in this group
        result.append(start)
        assigned.add(start['id'])
        while True:
            last_id = result[-1]['id']
            nxt = next(
                (p for p in posts if p.get('reply_to') == last_id and p['id'] not in assigned),
                None,
            )
            if nxt is None:
                break
            result.append(nxt)
            assigned.add(nxt['id'])

    # Append any remainder (should not happen in a valid chain)
    for post in sorted(posts, key=lambda p: p['timestamp']):
        if post['id'] not in assigned:
            result.append(post)

    return result


def _group_thread_posts(posts: list) -> list:
    """
    Group BlueSky self-reply chain posts within the same batch.

    Returns a list of groups (each group: list of posts sorted oldest-first).

    Strategy: use thread_root URI as the grouping key. Every reply post carries
    the same thread_root (the root post's URI), so posts belonging to the same
    thread are grouped together regardless of timestamp ties or missing
    intermediate posts in the feed.

    Root posts (no thread_root field) that are themselves the root of other posts
    in the batch are added to the same group as their replies.
    Posts with no thread relationship remain as single-post groups.
    """
    sorted_posts = sorted(posts, key=lambda p: p['timestamp'])
    post_by_id = {p['id']: p for p in sorted_posts}

    # Build groups keyed by thread_root URI
    thread_groups: dict = {}  # root_uri -> list of posts
    no_root_posts = []

    for post in sorted_posts:
        root_uri = post.get('thread_root')
        if root_uri:
            thread_groups.setdefault(root_uri, []).append(post)
        else:
            no_root_posts.append(post)

    # Root posts themselves may be in the batch (no thread_root on a root post)
    # Attach them to their own thread group if replies exist in this batch.
    assigned = set()
    for post in no_root_posts:
        post_id = post['id']
        if post_id in thread_groups:
            # This post is the root of a thread group already identified
            thread_groups[post_id].insert(0, post)
            assigned.add(post_id)

    groups = []

    # Emit thread groups ordered by reply chain (falls back to timestamp)
    for root_uri, group_posts in thread_groups.items():
        groups.append(_sort_group_by_reply_chain(group_posts))

    # Remaining posts with no thread_root and no replies in this batch
    for post in no_root_posts:
        if post['id'] not in assigned:
            groups.append([post])

    return groups


def main():
    """Main application entry point."""
    try:
        # Initialize core components
        print("🚀 Initializing Process BlueSky...")
        
        config = ConfigManager()
        state = StateManager()
        discord_notifier = DiscordNotifier(webhook_url=config.discord_webhook_url)
        logger = Logger(discord_notifier=discord_notifier)

        # Circuit breaker check — abort early if tripped
        if state.circuit_breaker_tripped:
            logger.error(
                f"🚨 Circuit breaker is TRIPPED — refusing to run.\n"
                f"Tripped at: {state.circuit_breaker_tripped_at}\n"
                f"Reason: {state.circuit_breaker_reason}\n"
                f"To reset: edit data/state.json and set circuit_breaker_tripped to false, "
                f"or run: python3 -c \"from process_bluesky.core.state_manager import StateManager; "
                f"s=StateManager(); s.reset_circuit_breaker(); print('Reset OK')\""
            )
            sys.exit(1)

        # Initialize services
        bluesky_service = BlueskyInputService(
            identifier=config.bluesky_identifier,
            password=config.bluesky_password
        )
        
        x_service = XOutputService(
            api_key=config.x_api_key,
            api_secret=config.x_api_secret,
            access_token=config.x_access_token,
            access_token_secret=config.x_access_token_secret,
            oauth2_client_id=config.x_oauth2_client_id,
            oauth2_client_secret=config.x_oauth2_client_secret,
            x_premium=config.x_premium
        )
        
        # Initialize Discord ebilog service (optional)
        discord_log_service = None
        if config.discord_log_webhook_url:
            discord_log_service = DiscordLogService(
                webhook_url=config.discord_log_webhook_url
            )

        content_processor = ContentProcessor(x_premium=config.x_premium)

        logger.info("Process BlueSky started successfully")
        logger.info(f"Polling interval: {config.polling_interval} seconds")
        logger.info(f"Target user: {config.bluesky_identifier}")
        x_limit = XOutputService.X_PREMIUM_MAX_LENGTH if config.x_premium else XOutputService.X_FREE_MAX_LENGTH
        logger.info(f"X mode: {'Premium (' + str(x_limit) + ' chars)' if config.x_premium else 'Free (280 chars, thread splitting enabled)'}")
        
        # Connect to services
        logger.info("Connecting to Bluesky...")
        if not bluesky_service.connect():
            logger.error("Failed to connect to Bluesky")
            return
        
        logger.info("Connecting to X...")
        if not x_service.connect():
            logger.error("Failed to connect to X")
            return
        
        if discord_log_service:
            logger.info("Discord えびログ output enabled")
        else:
            logger.info("Discord えびログ output disabled (no webhook URL)")

        logger.info("All services connected successfully!")
        
        # Check for posts to skip (for debugging)
        skip_post_ids = set()
        skip_env = os.environ.get('SKIP_POST_IDS', '')
        if skip_env:
            skip_post_ids = set(skip_env.split(','))
            logger.info(f"Will skip posts with IDs: {skip_post_ids}")
        
        logger.info("Starting single-run check...")

        # Counter for consecutive network errors
        consecutive_network_errors = 0
        NETWORK_ERROR_THRESHOLD = 5  # Notify Discord after this many consecutive errors

        while True:
            try:
                logger.info("Checking for new posts...")
                
                # Get latest posts from Bluesky
                since_timestamp = state.last_processed_at
                logger.info(f"Looking for posts newer than: {since_timestamp}")
                try:
                    posts = bluesky_service.get_latest_posts(since_timestamp=since_timestamp)
                    logger.info(f"Raw API returned {len(posts)} posts")
                except BlueskyServerError as e:
                    logger.error(
                        f"Bluesky API サーバー側エラー: {str(e)}\n"
                        f"【原因推測】Bluesky側のインフラ障害（502/503/504）。コード側の問題ではありません。\n"
                        f"【対応】次回実行時に自動リトライします。継続する場合は https://status.bsky.app/ を確認してください。"
                    )
                    sys.exit(0)
                except BlueskyRateLimitError as e:
                    logger.error(
                        f"Bluesky API レートリミット: {str(e)}\n"
                        f"【原因推測】API呼び出し回数が上限に達しました。\n"
                        f"【対応】次回実行時に自動リトライします。通常は数分で回復します。"
                    )
                    sys.exit(0)
                except BlueskyAuthError as e:
                    logger.error(
                        f"Bluesky API 認証エラー: {str(e)}\n"
                        f"【原因推測】認証情報が無効または期限切れです。\n"
                        f"【対応】.envファイルのBLUESKY_IDENTIFIER/PASSWORDを確認してください。"
                    )
                    sys.exit(1)
                except Exception as e:
                    error_msg = str(e) if str(e) else f"{type(e).__name__}: {repr(e)}"
                    # Check if this is a network error
                    is_network_error = 'NetworkError' in error_msg
                    if is_network_error:
                        consecutive_network_errors += 1
                        if consecutive_network_errors >= NETWORK_ERROR_THRESHOLD:
                            logger.error(
                                f"Failed to get posts from Bluesky API: {error_msg}\n"
                                f"（{consecutive_network_errors}回連続でネットワークエラーが発生しています）"
                            )
                        else:
                            # Use warning instead of error to avoid Discord notification
                            logger.warning(f"Bluesky API network error ({consecutive_network_errors}/{NETWORK_ERROR_THRESHOLD}): {error_msg}")
                    else:
                        logger.error(f"Failed to get posts from Bluesky API: {error_msg}")
                    sys.exit(0)

                # Reset network error counter on successful API call
                if consecutive_network_errors > 0:
                    logger.info(f"Network connection recovered after {consecutive_network_errors} error(s)")
                    # If we had notified about network errors, also notify about recovery
                    if consecutive_network_errors >= NETWORK_ERROR_THRESHOLD:
                        discord_notifier.send_success_notification(
                            title="Bluesky API 接続回復",
                            message=f"ネットワーク接続が回復しました。\n{consecutive_network_errors}回連続でエラーが発生していましたが、正常に復旧しました。"
                        )
                consecutive_network_errors = 0

                if posts:
                    logger.info(f"Found {len(posts)} new posts")

                    # Filter out already processed posts and determine per-destination needs
                    posts_to_process = []
                    for post in posts:
                        if post['id'] in skip_post_ids:
                            logger.info(f"🚫 Skipping post {post['id']} (in skip list)")
                            state.add_processed_post(post['id'], post['timestamp'])
                            continue

                        # Determine per-destination completion status
                        x_done = (
                            state.is_destination_completed(post['id'], 'x')
                            or state.is_post_permanently_failed(post['id'])
                        )
                        discord_done = (
                            state.is_destination_completed(post['id'], 'discord_log')
                            or state.is_discord_log_permanently_failed(post['id'])
                            or not discord_log_service
                        )

                        if x_done and discord_done:
                            logger.debug(f"Skipping fully completed post: {post['id']}")
                            continue

                        needs_x = not x_done
                        needs_discord = not discord_done

                        # Log retry info
                        if needs_x and state.is_post_failed(post['id']):
                            retry_count = state.get_failed_post_count(post['id'])
                            logger.info(f"🔄 Retrying X for post {post['id']} (attempt {retry_count + 1}/{state.max_retry_count})")
                        if needs_discord and state.is_discord_log_failed(post['id']):
                            retry_count = state.get_discord_log_failed_count(post['id'])
                            logger.info(f"🔄 Retrying Discord ebilog for post {post['id']} (attempt {retry_count + 1}/{state.max_retry_count})")

                        posts_to_process.append({
                            'post': post,
                            'needs_x': needs_x,
                            'needs_discord': needs_discord,
                        })

                    if posts_to_process:
                        logger.info(f"Found {len(posts_to_process)} posts to process out of {len(posts)} total")

                        # Sort oldest-first for correct thread processing
                        posts_to_process.sort(key=lambda item: item['post']['timestamp'])

                        # X Premium: build thread merging plan
                        # merged_x_posts: {post_id -> {'is_primary': bool, ...}}
                        merged_x_posts = {}
                        if config.x_premium:
                            needs_x_posts = [
                                item['post'] for item in posts_to_process if item['needs_x']
                            ]
                            for group in _group_thread_posts(needs_x_posts):
                                if len(group) > 1:
                                    merged_content = "\n\n".join(p['content'] for p in group)
                                    merged_images = [
                                        img for p in group for img in p.get('images', [])
                                    ]
                                    primary_id = group[0]['id']
                                    secondary_ids = [p['id'] for p in group[1:]]
                                    logger.info(
                                        f"🔀 X Premium: {len(group)}-part BlueSky thread → 1 X post "
                                        f"(primary: {primary_id[:50]}...)"
                                    )
                                    merged_x_posts[primary_id] = {
                                        'is_primary': True,
                                        'content': merged_content,
                                        'images': merged_images if merged_images else None,
                                        'secondary_ids': secondary_ids,
                                    }
                                    for sid in secondary_ids:
                                        merged_x_posts[sid] = {
                                            'is_primary': False,
                                            'primary_id': primary_id,
                                        }

                        for item in posts_to_process:
                            post = item['post']
                            try:
                                logger.info(f"Processing post: {post['id']}")
                                logger.info(f"Post content preview: {post['content'][:100]}{'...' if len(post['content']) > 100 else ''}")

                                # --- X posting (if needed) ---
                                if item['needs_x']:
                                    x_merge = merged_x_posts.get(post['id'])

                                    if x_merge and not x_merge['is_primary']:
                                        # Secondary post in a merged group.
                                        # X was handled by the primary — finalize only if primary succeeded.
                                        primary_id = x_merge['primary_id']
                                        primary_tweet_id = state.get_twitter_id_for_bluesky_post(primary_id)
                                        if primary_tweet_id:
                                            logger.info(
                                                f"🔀 X Premium: secondary post absorbed into merged tweet, marking X done"
                                            )
                                            state.mark_destination_completed(post['id'], 'x')
                                            state.add_post_mapping(post['id'], primary_tweet_id)
                                        else:
                                            # Primary hasn't posted yet (or failed) — leave for retry
                                            logger.info(
                                                f"🔀 X Premium: secondary post waiting for primary X post, will retry"
                                            )
                                    else:
                                        # Normal X posting, or primary of a merged group
                                        reply_to_tweet_id = None
                                        if 'reply_to' in post:
                                            parent_bluesky_id = post['reply_to']
                                            reply_to_tweet_id = state.get_last_twitter_id_for_bluesky_post(parent_bluesky_id)
                                            if reply_to_tweet_id:
                                                logger.info(f"🧵 This is a thread reply. Parent Bluesky: {parent_bluesky_id} -> Twitter: {reply_to_tweet_id}")
                                            else:
                                                logger.info(f"⚠️ Thread parent not found in mapping: {parent_bluesky_id}")

                                        # Determine content: merged (primary) or original
                                        if x_merge:
                                            raw_content = x_merge['content']
                                            logger.info(
                                                f"🔀 X Premium: posting merged content "
                                                f"({len(x_merge['secondary_ids']) + 1} BlueSky posts → 1 X post)"
                                            )
                                        else:
                                            raw_content = post['content']

                                        # Encode non-ASCII characters in URLs for X compatibility
                                        x_content = content_processor.encode_urls_for_x(raw_content)

                                        # Check if content needs splitting (too long for single tweet)
                                        content_chunks = content_processor.split_for_thread(x_content)
                                        needs_thread = len(content_chunks) > 1

                                        if needs_thread:
                                            logger.info(f"📝 Long content detected. Splitting into {len(content_chunks)} tweets")
                                            for i, chunk in enumerate(content_chunks):
                                                logger.info(f"   Chunk {i+1}: {chunk[:50]}... ({len(chunk)} chars)")

                                        # Prepare metadata with images if present
                                        post_metadata = {
                                            'source_id': post['id'],
                                            'source_platform': 'bluesky',
                                            'original_content': post['content']
                                        }
                                        if x_merge and x_merge.get('images'):
                                            post_metadata['images'] = x_merge['images']
                                            logger.info(f"Found {len(x_merge['images'])} image(s) across merged posts")
                                        elif 'images' in post:
                                            post_metadata['images'] = post['images']
                                            logger.info(f"Found {len(post['images'])} image(s) in post")

                                        logger.info(f"🚀 Attempting to post to X...")

                                        # Circuit breaker safety check
                                        state.pre_post_check(x_content)

                                        if needs_thread:
                                            result = x_service.post_thread(
                                                contents=content_chunks,
                                                metadata=post_metadata,
                                                reply_to_tweet_id=reply_to_tweet_id
                                            )
                                        else:
                                            result = x_service.post_content(
                                                content=content_chunks[0],
                                                metadata=post_metadata,
                                                reply_to_tweet_id=reply_to_tweet_id
                                            )

                                        if result['success']:
                                            post_url = result.get('url', f"ID: {result.get('id') or result.get('first_tweet_id')}")
                                            logger.info(f"Successfully posted to X: {post_url}")

                                            # Record for circuit breaker tracking
                                            if not result.get('skipped'):
                                                state.record_x_post(x_content)

                                            # Save mapping for primary and all merged secondary posts
                                            if needs_thread:
                                                first_id = result.get('first_tweet_id')
                                                last_id = result.get('last_tweet_id')
                                                if first_id and last_id:
                                                    state.add_post_mapping_with_last_tweet(post['id'], first_id, last_id)
                                                    logger.info(f"📌 Saved thread mapping: {post['id']} -> first:{first_id}, last:{last_id}")
                                                    if x_merge:
                                                        for sid in x_merge['secondary_ids']:
                                                            state.add_post_mapping_with_last_tweet(sid, first_id, last_id)
                                            else:
                                                tweet_id = result.get('id')
                                                if tweet_id:
                                                    state.add_post_mapping(post['id'], tweet_id)
                                                    logger.info(f"📌 Saved mapping: {post['id']} -> {tweet_id}")
                                                    if x_merge:
                                                        for sid in x_merge['secondary_ids']:
                                                            state.add_post_mapping(sid, tweet_id)

                                            state.mark_destination_completed(post['id'], 'x')
                                            state.remove_from_failed(post['id'])
                                        else:
                                            error_msg = result.get('error', 'Unknown error')
                                            logger.error(f"Failed to post to X: {error_msg}")
                                            permanently_failed = state.add_failed_post(
                                                post['id'], post['timestamp'], error_msg
                                            )
                                            retry_count = state.get_failed_post_count(post['id'])
                                            if permanently_failed:
                                                logger.error(
                                                    f"Post {post['id']} X permanently failed after {state.max_retry_count} retries."
                                                )
                                            else:
                                                logger.info(
                                                    f"Post {post['id']} X will be retried. "
                                                    f"Retry count: {retry_count}/{state.max_retry_count}"
                                                )

                                # --- Discord えびログ posting (if needed) ---
                                if item['needs_discord']:
                                    logger.info(f"📢 Attempting to post to Discord えびログ...")
                                    discord_result = discord_log_service.post_content(
                                        content=post['content'],
                                        metadata={
                                            'post_id': post['id'],
                                            'images': post.get('images', []),
                                        }
                                    )

                                    if discord_result['success']:
                                        logger.info(f"Successfully posted to Discord えびログ")
                                        state.mark_destination_completed(post['id'], 'discord_log')
                                        state.remove_from_discord_log_failed(post['id'])
                                    else:
                                        error_msg = discord_result.get('error', 'Unknown error')
                                        logger.error(f"Failed to post to Discord えびログ: {error_msg}")
                                        permanently_failed = state.add_discord_log_failed_post(
                                            post['id'], post['timestamp'], error_msg
                                        )
                                        if permanently_failed:
                                            logger.error(
                                                f"Post {post['id']} Discord ebilog permanently failed after {state.max_retry_count} retries."
                                            )

                                # Mark fully completed if all destinations done
                                if state.is_all_destinations_completed(post['id']):
                                    state.add_processed_post(post['id'], post['timestamp'])

                            except DuplicateContentSkipped as dup_err:
                                logger.warning(
                                    f"⏭️ Skipping duplicate post: {str(dup_err)}"
                                )
                                # Mark X as done (content already posted previously)
                                state.mark_destination_completed(post['id'], 'x')
                                state.remove_from_failed(post['id'])
                                if state.is_all_destinations_completed(post['id']):
                                    state.add_processed_post(post['id'], post['timestamp'])
                                continue
                            except CircuitBreakerTripped as cb_err:
                                logger.error(
                                    f"🚨 CIRCUIT BREAKER TRIPPED!\n"
                                    f"Reason: {str(cb_err)}\n"
                                    f"All X posting halted. Manual reset required.\n"
                                    f"Posts this run: {state._posts_this_run}"
                                )
                                # Force exit — do not process any more posts
                                sys.exit(1)
                            except Exception as e:
                                error_msg = str(e)
                                logger.error(f"Error processing post {post.get('id', 'unknown')}: {error_msg}")
                                # Track X failure if X was needed
                                if item['needs_x'] and not state.is_destination_completed(post['id'], 'x'):
                                    state.add_failed_post(post['id'], post['timestamp'], error_msg)
                                continue
                    else:
                        logger.info("All posts have already been processed")
                else:
                    logger.info("No new posts found")
                
                # Update last check time
                state.update_last_check()
                
                logger.info("Check completed")
                break

            except Exception as e:
                logger.error(f"Unexpected error during check: {str(e)}")
                sys.exit(0)

        # Cleanup connections
        logger.info("Disconnecting from services...")
        bluesky_service.disconnect()
        x_service.disconnect()
        
        logger.info("Process BlueSky stopped")
        
    except Exception as e:
        print(f"❌ Failed to start Process BlueSky: {str(e)}")
        sys.exit(1)


if __name__ == "__main__":
    main()