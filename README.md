# Switch2 Home Assistant Integration

A [Home Assistant](https://www.home-assistant.io/) custom integration for
[Switch2](https://www.switch2.co.uk/) district heating accounts.

Fetches meter readings and bill history from the Switch2 customer portal
(`my.switch2.co.uk`) and exposes them as Home Assistant sensors.

## Sensors

- **Meter reading** (per register) — energy sensor (kWh, `total_increasing`),
  compatible with the Home Assistant Energy Dashboard
- **Latest bill** — monetary sensor (GBP) showing the most recent bill amount

## Installation

### HACS (recommended)

1. Add this repository as a custom repository in HACS
2. Install "Switch2"
3. Restart Home Assistant
4. Go to Settings → Devices & Services → Add Integration → Search for "Switch2"
5. Enter your `my.switch2.co.uk` email and password

### Manual

Copy the `custom_components/switch2` directory into your Home Assistant
`config/custom_components/` directory and restart Home Assistant.

## Standalone API client

The `switch2` Python package can be used independently of Home Assistant:

```sh
pip install .
```

```python
import asyncio
from switch2 import Switch2ApiClient

async def main():
    client = Switch2ApiClient("email@example.com", "password")
    try:
        data = await client.fetch_data()
        print(data.customer)
        print(data.readings[0])
        print(data.bills[0])
    finally:
        await client.close()

asyncio.run(main())
```
