# Switch2 Home Assistant Integration

A [Home Assistant](https://www.home-assistant.io/) custom integration for
[Switch2](https://www.switch2.co.uk/) district heating accounts.

Fetches meter readings and bill history from the Switch2 customer portal
(`my.switch2.co.uk`) and exposes them as Home Assistant sensors.

## Sensors

- **Meter reading** for each register: the latest reading in kWh, with its
  date and its type as shown on the portal (for example *Automatic* or
  *Estimated*).
- **Latest bill**: the amount of the most recent bill, with its period,
  VAT, balance and a link to the PDF as attributes.
- **Account balance**: the current balance shown on the portal.
- One sensor per **line item** on the latest bill (for example *Heat* or
  *Heat Standing Charge*).

## Energy dashboard

The meter reading sensor only changes when Home Assistant polls the
portal, and readings can be days or weeks apart, particularly when they are
estimates. Rather than relying on that sensor, the integration writes two
statistics with the readings and bills on the days they belong to:

- `switch2:<account>_<register>_consumption`: the meter, spread evenly
  between readings. It is rewritten on every update, so estimates that are
  later corrected are picked up. The meter reading sensor shows the
  statistic ID in its `statistic_id` attribute.
- `switch2:<account>_cost`: the total of each bill including VAT, spread
  evenly over its billing period.

Home Assistant has no district heating source, so add the consumption
statistic under **Settings > Dashboards > Energy > Gas consumption**, and
choose *Use an entity tracking the total costs* with the cost statistic.

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
