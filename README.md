# LinkedIn Trend Watcher

A Flexus bot that monitors LinkedIn profiles for new posts and sends instant Slack alerts with analysis.

## Purpose

Track competitor activity on LinkedIn by monitoring specific profiles, detecting new posts, analyzing content, and tracking engagement metrics over time.

## Target Users

Marketing professionals, competitive intelligence analysts, and business leaders who need to stay updated on competitor content strategy and messaging.

## Core Functionality

### Monitoring
- Checks 3 LinkedIn profiles every 4 hours:
  - Kieran Flanagan (https://www.linkedin.com/in/kieranjflanagan/)
  - Liza Adams (https://www.linkedin.com/in/lizaadams/)
  - Andy Crestodina (https://www.linkedin.com/in/andycrestodina/)
- Scrapes profile activity using LinkedIn session cookies
- Stores post history in MongoDB to detect new content
- Tracks engagement metrics (likes, comments, shares) over time

### Analysis
- Categorizes posts by topic and content type
- Identifies mentions of priority keywords (AI, Marketing)
- Summarizes key messages and themes
- Highlights engagement patterns and spikes

### Alerting
- Sends immediate Slack DM to Katrin Maikova when new posts are detected
- Alert includes:
  - Post summary and categorization
  - Key topics identified
  - Current engagement metrics
  - Direct link to original post
  - Timestamp and author info

## User Interaction

### Setup Requirements
1. **LinkedIn Session Cookie**: User provides `li_at` cookie value for authenticated scraping
2. **Slack Bot Token**: OAuth token for sending DMs (format: `xoxb-...`)
3. **Slack User ID**: Target user ID for DMs (found in Slack profile)

### Commands (via Slack or Flexus UI)
- View current monitoring status
- Request manual scan of profiles
- View engagement history for specific profiles
- Pause/resume monitoring
- Add or remove profiles from watch list

### Scheduled Behavior
- **Every 4 hours**: Scan all profiles, detect new posts, send alerts
- **Daily**: Generate summary report of all activity
- **Weekly**: Analyze engagement trends and patterns

## Technical Architecture

### Data Storage
- **Policy Documents**: Store profile configurations, watch list, alert preferences
- **MongoDB Collections**:
  - `linkedin_posts`: Historical post data with engagement snapshots
  - `linkedin_profiles`: Profile metadata and last check timestamps
  - `engagement_history`: Time-series engagement data for trend analysis

### External Dependencies
- LinkedIn web scraping (no official API)
- Slack API for message delivery
- LLM for content analysis and summarization

### Error Handling
- LinkedIn rate limiting: Back off and retry with exponential delay
- Cookie expiration: Alert user via Slack to refresh credentials
- Network failures: Queue failed scans for retry
- Slack delivery failures: Fall back to Flexus UI notifications

## Success Criteria

- All new posts detected within 4-hour window
- Zero false positives (no duplicate alerts)
- Slack alerts delivered within 2 minutes of detection
- Analysis accurately identifies priority topics (AI, Marketing)
- Engagement tracking shows meaningful trend data
- Bot recovers gracefully from credential/network issues

## Future Enhancements

- Support for LinkedIn API when credentials are available
- Sentiment analysis of post content
- Competitive benchmarking (compare engagement across profiles)
- Content recommendation based on high-performing competitor posts
- Integration with additional messengers (Discord, Telegram)
- Custom alert rules (e.g., only alert if engagement > threshold)