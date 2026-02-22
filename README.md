[![hacs][hacs_badge]][hacs]

# Vigicrues Integration for Home Assistant

### Installation

Copy the `vigicrues` folder into `<config_dir>/custom_components/vigicrues/`.

### Configuration

#### Configuration via user interface (recommended)

1. Go to **Settings** → **Devices & Services**
2. Click **+ Add Integration**
3. Search for **Vigicrues**
4. Enter the stations you want to monitor (comma-separated), or leave empty to configure later
   - **With URLs**: `https://www.vigicrues.gouv.fr/station/F700000103, https://www.vigicrues.gouv.fr/station/F704000101`
   - **With IDs**: `F700000103, F704000101`
   - **Mixed**: `F700000103, https://www.vigicrues.gouv.fr/station/F704000101`
5. Click **Submit**

Station IDs can be found on https://www.vigicrues.gouv.fr/
You can also copy the URL directly from your browser.

To add, modify or remove stations after installation:
1. Go to **Settings** → **Devices & Services**
2. Find the **Vigicrues** integration
3. Click **Configure**

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
