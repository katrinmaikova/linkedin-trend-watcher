import asyncio
import logging
import json
import time
import re
from typing import Dict, Any, Optional, List
from datetime import datetime, timezone

import httpx
from bs4 import BeautifulSoup
from pymongo import AsyncMongoClient

from flexus_client_kit import ckit_client
from flexus_client_kit import ckit_cloudtool
from flexus_client_kit import ckit_bot_exec
from flexus_client_kit import ckit_shutdown
from flexus_client_kit import ckit_ask_model
from flexus_client_kit import ckit_mongo
from flexus_client_kit import ckit_kanban
from flexus_client_kit.integrations import fi_mongo_store
from linkedin_trend_watcher import linkedin_trend_watcher_install

logger = logging.getLogger("bot_linkedin_trend_watcher")

BOT_NAME = "linkedin_trend_watcher"
BOT_VERSION = "0.1.0"

SCAN_PROFILES_TOOL = ckit_cloudtool.CloudTool(
    strict=True,
    name="scan_profiles",
    description="Scan LinkedIn profiles for new posts and send alerts",
    parameters={
        "type": "object",
        "properties": {
            "force_scan": {"type": "boolean", "description": "Force immediate scan even if recently checked"},
        },
        "required": ["force_scan"],
        "additionalProperties": False,
    },
)

SEND_SLACK_ALERT_TOOL = ckit_cloudtool.CloudTool(
    strict=True,
    name="send_slack_alert",
    description="Send a Slack DM alert about a new LinkedIn post",
    parameters={
        "type": "object",
        "properties": {
            "author": {"type": "string", "description": "Post author name"},
            "category": {"type": "string", "description": "Post category"},
            "keywords": {"type": "string", "description": "Priority keywords found"},
            "summary": {"type": "string", "description": "Post summary"},
            "likes": {"type": "integer", "description": "Number of likes"},
            "comments": {"type": "integer", "description": "Number of comments"},
            "shares": {"type": "integer", "description": "Number of shares"},
            "post_url": {"type": "string", "description": "Link to original post"},
            "posted_at": {"type": "string", "description": "Post timestamp"},
        },
        "required": ["author", "category", "keywords", "summary", "likes", "comments", "shares", "post_url", "posted_at"],
        "additionalProperties": False,
    },
)

GET_MONITORING_STATUS_TOOL = ckit_cloudtool.CloudTool(
    strict=True,
    name="get_monitoring_status",
    description="Get current monitoring status and last check times",
    parameters={
        "type": "object",
        "properties": {},
        "required": [],
        "additionalProperties": False,
    },
)

TOOLS = [
    SCAN_PROFILES_TOOL,
    SEND_SLACK_ALERT_TOOL,
    GET_MONITORING_STATUS_TOOL,
    fi_mongo_store.MONGO_STORE_TOOL,
]


async def scrape_linkedin_profile(profile_url: str, cookie: str) -> Optional[List[Dict[str, Any]]]:
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        "Cookie": f"li_at={cookie}",
    }

    try:
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            response = await client.get(profile_url, headers=headers)

            if response.status_code == 401 or response.status_code == 403:
                logger.error("LinkedIn authentication failed - cookie expired")
                return None

            if response.status_code == 429:
                logger.warning("LinkedIn rate limit hit")
                return None

            if response.status_code != 200:
                logger.error(f"LinkedIn returned status {response.status_code}")
                return None

            soup = BeautifulSoup(response.text, "lxml")

            posts = []
            post_elements = soup.find_all("div", class_=re.compile(r"feed-shared-update-v2"))

            for idx, post_elem in enumerate(post_elements[:5]):
                try:
                    text_elem = post_elem.find("div", class_=re.compile(r"feed-shared-text"))
                    text = text_elem.get_text(strip=True) if text_elem else ""

                    likes_elem = post_elem.find("span", class_=re.compile(r"social-details-social-counts__reactions-count"))
                    likes = int(re.sub(r"\D", "", likes_elem.get_text())) if likes_elem and likes_elem.get_text() else 0

                    comments_elem = post_elem.find("button", {"aria-label": re.compile(r"comment", re.IGNORECASE)})
                    comments_text = comments_elem.get_text(strip=True) if comments_elem else "0"
                    comments = int(re.sub(r"\D", "", comments_text)) if re.search(r"\d", comments_text) else 0

                    shares = 0

                    time_elem = post_elem.find("time")
                    timestamp = time_elem.get("datetime") if time_elem and time_elem.get("datetime") else datetime.now(timezone.utc).isoformat()

                    post_link_elem = post_elem.find("a", href=re.compile(r"/feed/update/"))
                    post_url = post_link_elem.get("href") if post_link_elem else profile_url
                    if post_url.startswith("/"):
                        post_url = f"https://www.linkedin.com{post_url}"

                    post_id = re.search(r"urn:li:activity:(\d+)", str(post_elem))
                    post_id = post_id.group(1) if post_id else f"{profile_url}_{idx}"

                    posts.append({
                        "post_id": post_id,
                        "text": text[:1000],
                        "likes": likes,
                        "comments": comments,
                        "shares": shares,
                        "timestamp": timestamp,
                        "url": post_url,
                    })

                except Exception as e:
                    logger.warning(f"Error parsing post element: {e}")
                    continue

            return posts

    except Exception as e:
        logger.error(f"Error scraping LinkedIn profile: {e}")
        return None


async def send_slack_dm(token: str, user_id: str, message: str) -> bool:
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                "https://slack.com/api/chat.postMessage",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                },
                json={
                    "channel": user_id,
                    "text": message,
                },
            )

            data = response.json()
            if data.get("ok"):
                logger.info(f"Slack message sent successfully")
                return True
            else:
                logger.error(f"Slack API error: {data.get('error')}")
                return False

    except Exception as e:
        logger.error(f"Error sending Slack message: {e}")
        return False


async def linkedin_trend_watcher_main_loop(fclient: ckit_client.FlexusClient, rcx: ckit_bot_exec.RobotContext) -> None:
    setup = ckit_bot_exec.official_setup_mixing_procedure(linkedin_trend_watcher_install.linkedin_trend_watcher_setup_schema, rcx.persona.persona_setup)

    mongo_conn_str = await ckit_mongo.mongo_fetch_creds(fclient, rcx.persona.persona_id)
    mongo = AsyncMongoClient(mongo_conn_str)
    dbname = rcx.persona.persona_id + "_db"
    mydb = mongo[dbname]
    personal_mongo = mydb["personal_mongo"]
    linkedin_posts = mydb["linkedin_posts"]
    linkedin_profiles = mydb["linkedin_profiles"]
    engagement_history = mydb["engagement_history"]

    await linkedin_posts.create_index("post_id", unique=True)
    await linkedin_profiles.create_index("profile_url", unique=True)

    monitoring_enabled = {"value": True}

    @rcx.on_updated_message
    async def updated_message_in_db(msg: ckit_ask_model.FThreadMessageOutput):
        pass

    @rcx.on_updated_thread
    async def updated_thread_in_db(th: ckit_ask_model.FThreadOutput):
        pass

    @rcx.on_updated_task
    async def updated_task_in_db(t: ckit_kanban.FPersonaKanbanTaskOutput):
        pass

    @rcx.on_tool_call(SCAN_PROFILES_TOOL.name)
    async def toolcall_scan_profiles(toolcall: ckit_cloudtool.FCloudtoolCall, model_produced_args: Dict[str, Any]) -> str:
        if not monitoring_enabled["value"]:
            return "Monitoring is currently paused"

        force_scan = model_produced_args.get("force_scan", False)

        linkedin_cookie = setup.get("linkedin_cookie", "")
        if not linkedin_cookie:
            return "Error: LinkedIn cookie not configured in setup"

        profile_urls = setup.get("profile_urls", "").strip().split("\n")
        profile_urls = [url.strip() for url in profile_urls if url.strip()]

        if not profile_urls:
            return "Error: No profile URLs configured"

        results = []
        new_posts_found = 0

        for profile_url in profile_urls:
            logger.info(f"Scanning profile: {profile_url}")

            profile_record = await linkedin_profiles.find_one({"profile_url": profile_url})
            last_check = profile_record.get("last_check", 0) if profile_record else 0

            if not force_scan and time.time() - last_check < 3600:
                results.append(f"{profile_url}: Skipped (checked recently)")
                continue

            posts = await scrape_linkedin_profile(profile_url, linkedin_cookie)

            if posts is None:
                if profile_record and profile_record.get("cookie_expired"):
                    results.append(f"{profile_url}: Cookie expired (already notified)")
                else:
                    results.append(f"{profile_url}: Error (check logs)")
                    await linkedin_profiles.update_one(
                        {"profile_url": profile_url},
                        {"$set": {"cookie_expired": True, "last_check": time.time()}},
                        upsert=True,
                    )
                continue

            await linkedin_profiles.update_one(
                {"profile_url": profile_url},
                {"$set": {"last_check": time.time(), "cookie_expired": False}},
                upsert=True,
            )

            profile_new_posts = 0
            for post in posts:
                try:
                    await linkedin_posts.insert_one({
                        "post_id": post["post_id"],
                        "profile_url": profile_url,
                        "text": post["text"],
                        "likes": post["likes"],
                        "comments": post["comments"],
                        "shares": post["shares"],
                        "timestamp": post["timestamp"],
                        "url": post["url"],
                        "first_seen": time.time(),
                        "alert_sent": False,
                    })
                    profile_new_posts += 1
                    new_posts_found += 1

                    await engagement_history.insert_one({
                        "post_id": post["post_id"],
                        "likes": post["likes"],
                        "comments": post["comments"],
                        "shares": post["shares"],
                        "recorded_at": time.time(),
                    })

                except Exception as e:
                    logger.debug(f"Post already exists or error: {e}")

            results.append(f"{profile_url}: Found {profile_new_posts} new posts")

        summary = "\n".join(results)
        summary += f"\n\nTotal new posts: {new_posts_found}"

        if new_posts_found > 0:
            summary += "\n\nUse LLM analysis to review new posts and send alerts for each."

        return summary

    @rcx.on_tool_call(SEND_SLACK_ALERT_TOOL.name)
    async def toolcall_send_slack_alert(toolcall: ckit_cloudtool.FCloudtoolCall, model_produced_args: Dict[str, Any]) -> str:
        slack_token = setup.get("slack_bot_token", "")
        slack_user_id = setup.get("slack_user_id", "")

        if not slack_token or not slack_user_id:
            return "Error: Slack credentials not configured"

        message = f"""**New Post from {model_produced_args['author']}**

**Category**: {model_produced_args['category']}
**Keywords**: {model_produced_args['keywords']}
**Summary**: {model_produced_args['summary']}

**Engagement**:
- Likes: {model_produced_args['likes']}
- Comments: {model_produced_args['comments']}
- Shares: {model_produced_args['shares']}

**Link**: {model_produced_args['post_url']}

Posted: {model_produced_args['posted_at']}
"""

        success = await send_slack_dm(slack_token, slack_user_id, message)

        if success:
            return f"✓ Slack alert sent for post by {model_produced_args['author']}"
        else:
            await personal_mongo.insert_one({
                "type": "failed_alert",
                "alert_data": model_produced_args,
                "timestamp": time.time(),
            })
            return f"✗ Slack delivery failed - alert saved to MongoDB for review"

    @rcx.on_tool_call(GET_MONITORING_STATUS_TOOL.name)
    async def toolcall_get_monitoring_status(toolcall: ckit_cloudtool.FCloudtoolCall, model_produced_args: Dict[str, Any]) -> str:
        profile_urls = setup.get("profile_urls", "").strip().split("\n")
        profile_urls = [url.strip() for url in profile_urls if url.strip()]

        status_lines = []
        status_lines.append(f"Monitoring: {'Enabled' if monitoring_enabled['value'] else 'Paused'}")
        status_lines.append(f"Profiles configured: {len(profile_urls)}")
        status_lines.append("")

        for profile_url in profile_urls:
            profile_record = await linkedin_profiles.find_one({"profile_url": profile_url})
            if profile_record:
                last_check = profile_record.get("last_check", 0)
                time_ago = int(time.time() - last_check)
                minutes_ago = time_ago // 60
                status_lines.append(f"{profile_url}: Last checked {minutes_ago}m ago")
            else:
                status_lines.append(f"{profile_url}: Never checked")

        total_posts = await linkedin_posts.count_documents({})
        status_lines.append("")
        status_lines.append(f"Total posts tracked: {total_posts}")

        return "\n".join(status_lines)

    @rcx.on_tool_call(fi_mongo_store.MONGO_STORE_TOOL.name)
    async def toolcall_mongo_store(toolcall: ckit_cloudtool.FCloudtoolCall, model_produced_args: Dict[str, Any]) -> str:
        return await fi_mongo_store.handle_mongo_store(
            rcx.workdir,
            personal_mongo,
            toolcall,
            model_produced_args,
        )

    try:
        while not ckit_shutdown.shutdown_event.is_set():
            await rcx.unpark_collected_events(sleep_if_no_work=10.0)

    finally:
        logger.info("%s exit" % (rcx.persona.persona_id,))


def main():
    scenario_fn = ckit_bot_exec.parse_bot_args()
    fclient = ckit_client.FlexusClient(ckit_client.bot_service_name(BOT_NAME, BOT_VERSION), endpoint="/v1/jailed-bot")

    asyncio.run(ckit_bot_exec.run_bots_in_this_group(
        fclient,
        marketable_name=BOT_NAME,
        marketable_version_str=BOT_VERSION,
        bot_main_loop=linkedin_trend_watcher_main_loop,
        inprocess_tools=TOOLS,
        scenario_fn=scenario_fn,
        install_func=linkedin_trend_watcher_install.install,
    ))


if __name__ == "__main__":
    main()
