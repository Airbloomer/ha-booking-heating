# Heating from booking calendars (Home Assistant blueprint)

Heat a holiday rental from its booking calendars. Guests arrive to a warm home, the heating drops to eco when they leave, and nobody has to remember to touch the thermostat.

[![Open your Home Assistant instance and show the blueprint import dialog.](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2FAirbloomer%2Fha-booking-heating%2Fblob%2Fmain%2Fblueprints%2Fautomation%2Fairbloomer%2Fbooking_heating.yaml)

## What it does

Every 30 minutes it reads your booking calendars and picks one plan:

| Plan | Default | When |
|---|---|---|
| Occupied | 20 °C by day (05:00–22:00), 19 °C at night | During a stay, and during pre-heat |
| Empty, short gap | 17 °C | The gap between stays is under 5 days |
| Empty, long gap | 15 °C | The gap is 5 days or more, or nothing is booked |
| Outside the season | 5 °C (frost protection) | Outside 1 Nov–31 Mar, unless the season override is on |

**Pre-heat** starts when the time left before check-in is at most

```
start-up lag + (comfort temperature − indoor temperature) ÷ warm-up rate + safety margin
```

capped at the longest pre-heat (default 36 h). With the defaults (2.5 h, 0.5 °C/h, 3 h), a home at 15 °C starts pre-heating 15.5 h before check-in; at 18 °C, 9.5 h before. Once pre-heat starts it continues until check-in. If check-in falls inside the heating season, pre-heat runs even if it starts just before the season.

**Guests:** a change up to 21 °C stays until the next plan change; a set point above 21 °C is reset at the next run.

**Safety:** if any calendar fails to load, the plan isn't changed. If the thermostat is unavailable, the run is skipped. A failed write isn't recorded, so the next run retries. Nothing is written when the plan hasn't changed.

All the numbers above are settings.

## Setup

1. Add your booking calendars to Home Assistant, for example with the **Remote Calendar** integration and your Airbnb / Booking.com / website iCal export links. Treat those links as secrets: keep them in Home Assistant, not in this blueprint.
2. Create an **input_text** helper (Settings → Devices & services → Helpers) for the automation's state. Optionally create an **input_boolean** for the season override.
3. Import the blueprint (button above), create an automation from it, pick your thermostat, calendars and helpers.
4. Start with **Dry run** on: it logs what it would do in the logbook without touching the thermostat. Turn it off when the plans look right.

### Tuning the warm-up rate

The default rate (0.5 °C/h) suits floor heating. The best value is your own: note the indoor temperature when pre-heat starts on a cold arrival and how long it takes to reach the comfort temperature, then set the rate to `degrees gained ÷ hours`, excluding the start-up lag. A flat between heated neighbours cools slowly, so its pre-heat is short; a detached house or top floor needs longer.

### Calendars

Events are treated as all-day stays from the check-in day to the check-out day, using the check-in and check-out times you set (defaults 16:00 and 11:00). Events whose title contains an ignored keyword (default `not available, blocked`) are skipped, so owner blocks don't heat the home.

### Thermostats

- **Most thermostats:** `set_temperature` mode calls `climate.set_temperature`, switching between day and night set points at the times you choose.
- **Finder Bliss 2:** `finderblissha_schedule` mode writes a weekly schedule through the [Finder Bliss integration](https://github.com/condatek/finderblissha) `set_schedule` service (manual set points switch a Bliss 2 off). Needs a version with `set_schedule`.

## Notes

- Check your local rules on maximum indoor temperatures (for example, Italy caps heating at 20 °C, +2 °C tolerance, in most buildings). The defaults stay at or below 20 °C.
- The blueprint never switches a boiler on or off directly; it only changes the thermostat.

## License

MIT
