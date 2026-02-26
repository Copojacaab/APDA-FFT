# APDA-FFT
Adaptive Peak Detection for FFT-based Structural Monitoring

## Configurazione e Deploy
Il sistema e' progettato per essere eseguito su un gateway Digi IX15 con sistema di comunicazione Xbee integrato.

### Prerequisiti 
- python 3.xODR
- modulo hw xbee interfaccia e accessibile

### Struttura delle Directory
Il software si aspetta una struttura specifica dell'ambiente di lavoro, che di default punta alla directory `/etc/config/scripts`:

```
    /etc/config/scripts/
    ├── gw_config.json         # File di configurazione principale
    ├── config.txt             # Configurazioni hardware per i singoli sensori
    ├── SHM_Data/              # Cartella di lavoro per l'I/O dei dati
    │   ├── history.log        # Log delle operazioni di sistema
    │   └── devices.txt        # Anagrafica e delay dei dispositivi connessi
    ├── GT_FFT_v2.py           # Core Application
    ├── metrics/
    │   └── fft_iterativa.py
    └── utils/
        ├── load_data.py
        ├── get_peak_prominence.py
        ├── get_peak_resolution.py
        ├── ftp_manager.py
        └── influxdb_manager.py
```

### Configurazione di sistema
Per evitare credenziali hardcoded, queste vengono gestite tramite il file `gw_config.json`. Prima di avviare il gateway va OBBLIGATORIAMENTE creato il file `gw_create.json` con la struttura:

```
{
    "ftp": {
        "server": "ftp.tuoserver.it",
        "user": "nome_utente",
        "pwd": "password_sicura",
        "path": "percorso/server/SHM_Files"
    },
    "influxdb": {
        "url": "http://IP_INFLUX:8086/api/v2/write?org=ORG_ID&bucket=NOME_BUCKET&precision=ms",
        "token": "IL_TUO_TOKEN_INFLUXDB"
    },
    "gateway": {
        "logger_file": "/etc/config/scripts/SHM_Data/history.log",
        "device_file": "/etc/config/scripts/SHM_Data/devices.txt",
        "config_file": "/etc/config/scripts/config.txt",
        "is_flexibile_structure": true
    }
}
```

NOTA: `is_flexbile_structure` definisce quale metodo di peak detection utilizzare:
    - True per strutture "flessibili" (ponti, passerelle)
    - False per strutture "rigide" (gallerie, edifici)

### Start
Una volta creata l'opportuna struttura delle directory e il file di configurazione si puo' avviare il sistema tramite l'esecuzione del file `GT_FFT_v3.py`

