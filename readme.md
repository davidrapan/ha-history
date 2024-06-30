# History Services integration

This integration povides easy way to export history data of any sensor using services

## Services
- Export
- Device tracker export

### Export

Id: 'history_services.export'  
Returns all the historical data of selected entity within given time interval

### Device tracker export

Id: 'history_services.export_device_tracker'  
Returns historical data of selected entity of the 'device_tracker' domain in the KML file format  
Saves output into file with default location: 'www/history/device_tracker.kml'

## Installation

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=davidrapan&repository=ha-history&category=integration)

### HACS (Manually)
- Follow the link [here](https://hacs.xyz/docs/faq/custom_repositories/)
- Add custom repository: https://github.com/davidrapan/ha-history
- Select type of the category: integration
- Find newly added History Services, open it and then click on the DOWNLOAD button

### Manually
- Copy the contents of 'custom_components/history_services' directory into the Home Assistant with exactly the same hirearchy withing the '/config' directory

### Configuration

Register services by placing 'history_services:' into the '/config/configuration.yaml'