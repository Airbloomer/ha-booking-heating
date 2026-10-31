# Heating from booking calendars (Home Assistant blueprint)

Heat a holiday rental from its booking calendars. Guests arrive to a warm home, the heating drops to eco when they leave, and nobody has to remember to touch the thermostat.

[![Open your Home Assistant instance and show the blueprint import dialog.](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2FAirbloomer%2Fha-booking-heating%2Fblob%2Fmain%2Fblueprints%2Fautomation%2Fairbloomer%2Fbooking_heating.yaml)

## What it does

Every 30 minutes it reads your booking calendars and picks one plan:

| Plan | Default | When |
|---|---|---|
| Occupied | 20 °C by day (05:00–22:00), 19 °C at night | During a stay, and during pre-heat |
| Empty, short gap | 17 °C | The gap between stays is under 5 days |
| Empty, long gap | 15 °C | The gap is 5 days or more, nothing is booked, or nobody checked out in the last 60 days |
| Outside the season | 5 °C (frost protection) | Outside 1 Nov–31 Mar, unless the season override is on |

**Pre-heat** starts when the time left before check-in is at most

```
start-up lag + (comfort temperature − indoor temperature) ÷ warm-up rate + safety margin
```

capped at the longest pre-heat (default 36 h). With the defaults (2.5 h, 0.5 °C/h, 3 h), a home at 15 °C starts pre-heating 15.5 h before check-in; at 18 °C, 9.5 h before. Once pre-heat starts it continues until check-in. Whether to pre-heat depends on the check-in date: an arrival inside the heating season is pre-heated even if pre-heat starts before the season does, and an arrival outside it is not.

**Guests:** a set point above 21 °C (or above your comfort temperatures, if those are higher) is reset at the next run. Smaller changes are kept until the next plan change; in `set_temperature` mode also until the next day/night switch, because that is a new write.

**Safety:** if any calendar fails to load (missing from the response or unavailable), the plan isn't changed. A calendar integration that keeps serving its last good copy after a failed refresh can't be detected this way, so consider an alert on your calendar entities. If the thermostat is unavailable, the run is skipped. A failed write isn't recorded, so the next run retries. Nothing is written when the plan hasn't changed.

All the numbers above are settings. The day must start before the night does (e.g. 05:00 and 22:00). Season dates are `MM-DD` with two digits each; an invalid value means "heat all year", so a typo never leaves a home on frost protection.

## Setup

1. Add your booking calendars to Home Assistant, for example with the **Remote Calendar** integration and your Airbnb / Booking.com / website iCal export links. Treat those links as secrets: keep them in Home Assistant, not in this blueprint.
2. Create an **input_text** helper (Settings → Devices & services → Helpers) for the automation's state. Optionally create an **input_boolean** for the season override.
3. Import the blueprint (button above), create an automation from it, pick your thermostat, calendars and helpers.
4. Start with **Dry run** on: it logs what it would do in the logbook without touching the thermostat. Turn it off when the plans look right. (In dry run nothing is stored, so the same line repeats every 30 minutes.)
5. Leave the thermostat in heating mode. The automation changes set points or schedules, never the HVAC mode, so a thermostat switched off stays off.

Requires Home Assistant 2024.10 or later.

### Tuning the warm-up rate

The default rate (0.5 °C/h) suits floor heating. The best value is your own: note the indoor temperature when pre-heat starts on a cold arrival and how long it takes to reach the comfort temperature, then set the rate to `degrees gained ÷ hours`, excluding the start-up lag. A flat between heated neighbours cools slowly, so its pre-heat is short; a detached house or top floor needs longer.

### Calendars

Events are treated as all-day stays from the check-in day to the check-out day, using the check-in and check-out times you set (defaults 16:00 and 11:00). Events whose title contains an ignored keyword (default `not available, blocked`) are skipped, so owner blocks don't heat the home.

### Thermostats

- **Most thermostats:** `set_temperature` mode calls `climate.set_temperature`, switching between day and night set points at the times you choose.
- **Finder Bliss 2:** `finderblissha_schedule` mode writes a weekly schedule through the Finder Bliss integration's `set_schedule` service (manual set points switch a Bliss 2 off). That service is in [Airbloomer/finderblissha](https://github.com/Airbloomer/finderblissha) v0.5.8 and later (installable as a HACS custom repository) and proposed upstream in [condatek/finderblissha#17](https://github.com/condatek/finderblissha/pull/17). With a version that lacks it, every write fails and nothing changes.

## Notes

- Check your local rules on maximum indoor temperatures (for example, Italy caps heating at 20 °C, +2 °C tolerance, in most buildings). The defaults stay at or below 20 °C.
- The blueprint never switches a boiler on or off directly; it only changes the thermostat.

## License

MIT
