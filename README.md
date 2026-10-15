# CarGoRuqsat stats Telegram bot

Parses https://cgr.qoldau.kz/ru/information/stat (server-rendered HTML) and answers with statistics on command.

## Setup
```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
export TELEGRAM_BOT_TOKEN="123456:ABC..."   # from @BotFather; never commit it
python bot.py
```

## Commands
- `/start`, `/help` – help
- `/stats` – summary: registered users (+7 days), bookings and users with passes (+last month), budget payments per year, registry counters
- `/posts` – free slots at every border crossing (today and total over open days, 1 МРП / 100 МРП)
- `/post <name>` – one crossing with the next 14 days, fuzzy name match (e.g. `/post хоргос`)

Page fetches are cached for 5 minutes.

## Parser only
```bash
python parser.py            # live page, JSON output
python parser.py stat.html  # local copy
python parser.py --full     # include all days per crossing
```

## Notes
- Post load comes from tooltip data on each day square (`title` attribute: free slots for 1 and 100 МРП) and the `zag-level-N` CSS class (raw load level).
- Per-payment-size (1/20/100 МРП) budget totals are only available via the site's POST filter form, which needs an anti-forgery session; the default page shows all sizes combined.
