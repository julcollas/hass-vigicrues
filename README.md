[![hacs][hacs_badge]][hacs]

# Vigicrues Integration for Home Assistant

### Installation

Copy the `vigicrues` folder into `<config_dir>/custom_components/vigicrues/`.

### Configuration

#### Configuration via user interface (recommended)

1. Go to **Settings** → **Devices & Services**
2. Click **+ Add Integration**
3. Search for **Vigicrues**
4. Search by place or watercourse and select one or more stations, or choose manual entry for station IDs or URLs
   - **With URLs**: `https://www.vigicrues.gouv.fr/station/F700000103, https://www.vigicrues.gouv.fr/station/F704000101`
   - **With IDs**: `F700000103, F704000101`
   - **Mixed**: `F700000103, https://www.vigicrues.gouv.fr/station/F704000101`
5. Click **Submit**

Hub'Eau search results are checked against Vigicrues before setup. Some stations
may not be available through Vigicrues; if validation fails, adjust the
selection or use manual entry.

Station IDs can be found on https://www.vigicrues.gouv.fr/
You can also copy the URL directly from your browser.

To add, modify or remove stations after installation:
1. Go to **Settings** → **Devices & Services**
2. Find the **Vigicrues** integration
3. Click **Configure**, then choose **Search or add a station**, **Update interval**, or **Remove stations**

Search by place or watercourse to find stations through Hub'Eau. Selected,
Vigicrues-compatible stations are added to the existing list. Manual station IDs
or URLs can also be added, and one or more stations can be removed from the list.

#### Update interval

The integration refreshes station data every 30 minutes by default. In the
integration options, choose a 15-, 30-, or 60-minute interval. A shorter
interval uses more API requests.

#### Configuration via YAML (legacy method, still supported)

Add the following lines to your `configuration.yaml`:

```yaml
# Example configuration.yaml entry

sensor:
  - platform: vigicrues
    stations:
      - F700000103
      - F704000101
```

## Screenshots

![entities](screenshots/entities.png)
![graph](screenshots/graph.png)

[hacs]: https://github.com/custom-components/hacs
[hacs_badge]: https://img.shields.io/badge/HACS-Custom-41BDF5.svg?style=for-the-badge
