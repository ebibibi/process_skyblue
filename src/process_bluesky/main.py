"""
Main entry point for Process BlueSky.

Runs once per invocation: checks for new BlueSky posts and mirrors them to the
Discord えびログ channel.  Designed to be called repeatedly by an external
scheduler (e.g. every 60 seconds).

X (Twitter) output was removed on 2026-07-31: posting to X is no longer done at
all, so neither the API path nor the Web Intent path exists any more.
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
from process_bluesky.services.discord_log_service import DiscordLogService


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

        # Discord えびログ is the only destination — without it there is nothing to do
        if not config.discord_log_webhook_url:
            logger.error(
                "DISCORD_LOG_WEBHOOK_URL is not set. えびログ is the only output "
                "destination, so there is nothing to do."
            )
            sys.exit(1)

        discord_log_service = DiscordLogService(
            webhook_url=config.discord_log_webhook_url
        )

        logger.info("Process BlueSky started successfully")
        logger.info(f"Polling interval: {config.polling_interval} seconds")
        logger.info(f"Target user: {config.bluesky_identifier}")
        logger.info("Output: Discord えびログ only (X output removed)")

        # Connect to services
        logger.info("Connecting to Bluesky...")
        if not bluesky_service.connect():
            logger.error("Failed to connect to Bluesky")
            return

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
                    error_msg = BlueskyInputService._describe_exception_chain(e)
                    is_network_error = BlueskyInputService._is_transient_error(e)
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

                        if state.is_destination_terminal(post['id'], 'discord_log'):
                            logger.debug(f"Skipping fully completed post: {post['id']}")
                            continue

                        if state.is_discord_log_failed(post['id']):
                            retry_count = state.get_discord_log_failed_count(post['id'])
                            logger.info(f"🔄 Retrying Discord ebilog for post {post['id']} (attempt {retry_count + 1}/{state.max_retry_count})")

                        posts_to_process.append({'post': post})

                    if posts_to_process:
                        logger.info(f"Found {len(posts_to_process)} posts to process out of {len(posts)} total")

                        # Sort oldest-first for correct thread processing
                        posts_to_process.sort(key=lambda item: item['post']['timestamp'])

                        for item in posts_to_process:
                            post = item['post']
                            try:
                                logger.info(f"Processing post: {post['id']}")
                                logger.info(f"Post content preview: {post['content'][:100]}{'...' if len(post['content']) > 100 else ''}")

                                logger.info(f"📢 Attempting to post to Discord えびログ...")

                                # Guards against a runaway loop re-sending the same
                                # batch: rate limit + duplicate-content detection.
                                state.pre_post_check(post['content'])

                                discord_result = discord_log_service.post_content(
                                    content=post['content'],
                                    metadata={
                                        'post_id': post['id'],
                                        'images': post.get('images', []),
                                    }
                                )

                                if discord_result['success']:
                                    logger.info(f"Successfully posted to Discord えびログ")
                                    state.record_post(post['content'])
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
                                # Content was already mirrored — treat as done
                                state.mark_destination_completed(post['id'], 'discord_log')
                                state.remove_from_discord_log_failed(post['id'])
                                if state.is_all_destinations_completed(post['id']):
                                    state.add_processed_post(post['id'], post['timestamp'])
                                continue
                            except CircuitBreakerTripped as cb_err:
                                logger.error(
                                    f"🚨 CIRCUIT BREAKER TRIPPED!\n"
                                    f"Reason: {str(cb_err)}\n"
                                    f"All えびログ posting halted. Manual reset required.\n"
                                    f"Posts this run: {state._posts_this_run}"
                                )
                                # Force exit — do not process any more posts
                                sys.exit(1)
                            except Exception as e:
                                error_msg = str(e)
                                logger.error(f"Error processing post {post.get('id', 'unknown')}: {error_msg}")
                                if not state.is_destination_completed(post['id'], 'discord_log'):
                                    state.add_discord_log_failed_post(
                                        post['id'], post['timestamp'], error_msg
                                    )
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

        logger.info("Process BlueSky stopped")
        
    except Exception as e:
        print(f"❌ Failed to start Process BlueSky: {str(e)}")
        sys.exit(1)


if __name__ == "__main__":
    main()
