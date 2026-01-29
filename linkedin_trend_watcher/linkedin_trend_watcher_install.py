import asyncio
import base64
import json
from pathlib import Path

from flexus_client_kit import ckit_client, ckit_bot_install
from flexus_client_kit import ckit_cloudtool

from linkedin_trend_watcher import linkedin_trend_watcher_prompts


BOT_DESCRIPTION = """
## LinkedIn Trend Watcher - Competitive Intelligence Bot

Monitor competitor activity on LinkedIn with automated tracking, analysis, and instant Slack alerts.

**Key Features:**
- **Automated Monitoring**: Scans configured LinkedIn profiles every 4 hours
- **Smart Detection**: Identifies new posts and tracks engagement metrics (likes, comments, shares)
- **AI Analysis**: Categorizes posts by topic, identifies priority keywords (AI, Marketing), summarizes key messages
- **Instant Alerts**: Sends Slack DM notifications immediately when new posts are detected
- **Engagement Tracking**: Monitors metrics over time to identify trends and spikes
- **Zero Duplicates**: MongoDB storage prevents repeat alerts for the same post

**Perfect for:**
- Marketing teams tracking competitor content strategy
- Competitive intelligence analysts
- Business leaders monitoring industry thought leaders
- Growth teams identifying successful content patterns

**What You'll Get:**
- Real-time awareness of competitor posts within 4-hour window
- Structured analysis of post content and engagement
- Historical data for trend analysis
- Reliable alerting with graceful error handling

**Setup Requirements:**
- LinkedIn session cookie (li_at) for authenticated access
- Slack bot token for sending DMs
- Slack user ID for alert destination
- List of LinkedIn profile URLs to monitor
"""


linkedin_trend_watcher_setup_schema = [
    {
        "bs_name": "linkedin_cookie",
        "bs_type": "string_long",
        "bs_default": "",
        "bs_group": "LinkedIn Configuration",
        "bs_order": 1,
        "bs_importance": 2,
        "bs_description": "LinkedIn session cookie (li_at value). Find this in your browser cookies after logging into LinkedIn.",
        "bs_placeholder": "AQEDARxxxxxx...",
    },
    {
        "bs_name": "profile_urls",
        "bs_type": "string_multiline",
        "bs_default": "https://www.linkedin.com/in/katrin-maikova/\nhttps://www.linkedin.com/in/kieranjflanagan/\nhttps://www.linkedin.com/in/lizaadams/\nhttps://www.linkedin.com/in/andycrestodina/",
        "bs_group": "LinkedIn Configuration",
        "bs_order": 2,
        "bs_importance": 2,
        "bs_description": "LinkedIn profile URLs to monitor (one per line)",
    },
    {
        "bs_name": "slack_bot_token",
        "bs_type": "string_long",
        "bs_default": "",
        "bs_group": "Slack Configuration",
        "bs_order": 1,
        "bs_importance": 2,
        "bs_description": "Slack bot token for sending DMs (format: xoxb-...)",
        "bs_placeholder": "xoxb-YOUR-TOKEN-HERE",
    },
    {
        "bs_name": "slack_user_id",
        "bs_type": "string_short",
        "bs_default": "",
        "bs_group": "Slack Configuration",
        "bs_order": 2,
        "bs_importance": 2,
        "bs_description": "Slack user ID to send alerts to (format: U01234ABCDE). Find this in Slack profile.",
        "bs_placeholder": "U01234ABCDE",
    },
    {
        "bs_name": "check_interval_hours",
        "bs_type": "int",
        "bs_default": 4,
        "bs_group": "Monitoring Settings",
        "bs_order": 1,
        "bs_importance": 1,
        "bs_description": "How often to check profiles for new posts (in hours)",
    },
]


LINKEDIN_TREND_WATCHER_DEFAULT_LARK = """
print("Processing %d messages" % len(messages))
"""


async def install(
    client: ckit_client.FlexusClient,
    ws_id: str,
    bot_name: str,
    bot_version: str,
    tools: list[ckit_cloudtool.CloudTool],
):
    bot_internal_tools = json.dumps([t.openai_style_tool() for t in tools])
    pic_big = base64.b64encode(open(Path(__file__).with_name("linkedin_trend_watcher-1024x1536.webp"), "rb").read()).decode("ascii")
    pic_small = base64.b64encode(open(Path(__file__).with_name("linkedin_trend_watcher-256x256.webp"), "rb").read()).decode("ascii")

    await ckit_bot_install.marketplace_upsert_dev_bot(
        client,
        ws_id=ws_id,
        marketable_name=bot_name,
        marketable_version=bot_version,
        marketable_accent_color="#0077B5",
        marketable_title1="LinkedIn Trend Watcher",
        marketable_title2="Monitor competitor LinkedIn activity with automated tracking and instant Slack alerts.",
        marketable_author="Flexus",
        marketable_occupation="Competitive Intelligence Analyst",
        marketable_description=BOT_DESCRIPTION,
        marketable_typical_group="Marketing / Intelligence",
        marketable_github_repo="",
        marketable_run_this="python -m linkedin_trend_watcher.linkedin_trend_watcher_bot",
        marketable_setup_default=linkedin_trend_watcher_setup_schema,
        marketable_featured_actions=[
            {"feat_question": "Show monitoring status", "feat_expert": "default", "feat_depends_on_setup": ["linkedin_cookie"]},
            {"feat_question": "Scan profiles now", "feat_expert": "default", "feat_depends_on_setup": ["linkedin_cookie", "profile_urls"]},
        ],
        marketable_intro_message="Hi! I'm LinkedIn Trend Watcher. I'll monitor the LinkedIn profiles you configure and send you instant Slack alerts when new posts are detected. Configure your LinkedIn cookie and Slack credentials in setup to get started.",
        marketable_preferred_model_default="grok-4-1-fast-non-reasoning",
        marketable_daily_budget_default=100_000,
        marketable_default_inbox_default=10_000,
        marketable_experts=[
            ("default", ckit_bot_install.FMarketplaceExpertInput(
                fexp_system_prompt=linkedin_trend_watcher_prompts.linkedin_trend_watcher_prompt,
                fexp_python_kernel=LINKEDIN_TREND_WATCHER_DEFAULT_LARK,
                fexp_block_tools="",
                fexp_allow_tools="*",
                fexp_app_capture_tools=bot_internal_tools,
                fexp_description="Main expert that monitors LinkedIn profiles, analyzes posts, and sends Slack alerts.",
            )),
        ],
        marketable_tags=["LinkedIn", "Monitoring", "Slack", "Competitive Intelligence"],
        marketable_picture_big_b64=pic_big,
        marketable_picture_small_b64=pic_small,
        marketable_schedule=[
            {
                "sched_type": "SCHED_CREATE_TASK",
                "sched_when": "EVERY:4h",
                "sched_first_question": "Scan all configured LinkedIn profiles for new posts. For each new post, analyze the content and send a Slack alert.",
            },
        ],
    )


if __name__ == "__main__":
    from linkedin_trend_watcher import linkedin_trend_watcher_bot
    args = ckit_bot_install.bot_install_argparse()
    client = ckit_client.FlexusClient("linkedin_trend_watcher_install")
    asyncio.run(install(client, ws_id=args.ws, bot_name=linkedin_trend_watcher_bot.BOT_NAME, bot_version=linkedin_trend_watcher_bot.BOT_VERSION, tools=linkedin_trend_watcher_bot.TOOLS))
