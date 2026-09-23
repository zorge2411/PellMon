PellMon
=======
![logo](https://raw.github.com/motoz/PellMon/master/src/Pellmonweb/media/img/favicon-160x160.png)

> [!IMPORTANT]
> **Production deployment of PellMon is Linux-only.** Core hardware and communication subsystems require Linux-specific facilities (D-Bus system/session bus, PyGObject/GLib main loops, RRDtool C-bindings, Linux serial devices `/dev/ttyUSB*`, and GPIO). Windows is supported for development, mock-based testing, and syntax verification only.

PellMon is logging, monitoring and configuration solution for pellet burners. It consists of a backend server daemon, which
uses RRDtool as a logging database, and a frontend daemon providing a responsive mobile friendly web based user interface. 
Additionally there is a command line tool for interfacing with the server and web based configuration tool.

PellMon can communicate directly with a supported pellet burner, or it can use a feeder-auger revolution counter as
base for pellet consumption calculation.

PellMon uses plugins to provide data about your burner. The most fully featured plugins are **ScotteCom**, which enables communication 
with a NBE scotte/woody/biocomfort V4, V5 or V6 pellet burner and **NBEcom** for the newer NBE V7/10/13 controllers. They give you access to all configuration parameters and measurement data, and also handles logging of alarms and mode/setting changes.

The plugin system makes it easy to add custom plugins for extended functionality, a 'template' plugin is provided as an example
along with the other preinstalled plugins:

**PelletCalc** Calculated power value and pellet consumption from a feeder auger counter.

**RaspberryPi** Access inputs and outputs on the raspberry pi single board computer. One input can be configured
as a counter to provide a base for pellet consumption calculation. It also provides general I/O, and a tachometer input that can be used
to measure the blower speed, by interfacing to the blowers tacho output or by using an optical detector.

**OWFS** Communicate with an owserver. Can be used to read onewire sensors, for instance temperature. It can also use a 
onewire input (ds2460 based) to count feeder auger revolutions for use with the PelletCalc plugin. 

**Consumption** Calculate and graph hourly, weekly, monthly and yearly fuel consumption.

**CustomAlarms** Create an unlimited number of limits to watch on available data, optionally send email when a limit is exceeded.

**Calculate** A simple script engine to to calcualate new values based on the existing data and automate things.

**SiloLevel** Calculate and graph the pellet silo level from the fill-up time to current time.

**Cleaning** Calculate how much fuel is burned since the boiler was last cleaned.

**Onewire** Read onewire sensor data using the kernel driver interface /sys/bus/w1/

**NBEcom** Connect to an NBE V7/V13 pellet burner over ethernet

**Heatingcircuit** Automatically set the heating circuit mixing valve according to current outside temperature

**Openweathermap** Read current temperature at your location from openweathermap.com

**Exec** The Exec plugin calls external commands when reading/writing items

Plugin documentation is found in the configuration file at plugins/plugin-name.conf

#### Contains:

### pellmonsrv:
Communication daemon. Implements a DBUS interface for reading and writing setting values and reading of measurement data. Optionally handles logging of measurement data to an RRD database. 
<pre>
usage: pellmonsrv.py [-h] [-P PIDFILE] [-U USER] [-G GROUP] [-C CONFIG] [-D {SESSION,SYSTEM}] [-p PLUGINDIR]
                  {debug,start,stop,restart}

positional arguments:
  {debug,start,stop,restart}
                        With debug argument pellmonsrv won't daemonize

optional arguments:
  -h, --help            show this help message and exit
  -P PIDFILE, --PIDFILE PIDFILE
                        Full path to pidfile
  -U USER, --USER USER  Run as USER
  -G GROUP, --GROUP GROUP
                        Run as GROUP
  -C CONFIG, --CONFIG CONFIG
                        Full path to config file
  -D {SESSION,SYSTEM}, --DBUS {SESSION,SYSTEM}
                        which bus to use, SESSION is default
  -p PLUGINDIR, --PLUGINDIR PLUGINDIR
                        Full path to plugin directory
</pre>

### pellmonweb:
Webserver and webapp, plotting of measurement, calculated consumption and data and parameter reading/writing.
<pre>
usage: pellmonweb.py [-h] [-D] [-P PIDFILE] [-U USER] [-G GROUP] [-C CONFIG] [-d {SESSION,SYSTEM}]

optional arguments:
  -h, --help            show this help message and exit
  -D, --DAEMONIZE       Run as daemon
  -P PIDFILE, --PIDFILE PIDFILE
                        Full path to pidfile
  -U USER, --USER USER  Run as USER
  -G GROUP, --GROUP GROUP
                        Run as GROUP
  -C CONFIG, --CONFIG CONFIG
                        Full path to config file
  -d {SESSION,SYSTEM}, --DBUS {SESSION,SYSTEM}
                        which bus to use, SESSION is default
</pre>

### pellmoncli:
Interactive command line client with tab completion. Reading and writing of setting values, and reading of measurement data.

    usage: pellmoncli.py [-h] {get,set,list,i}

### pellmonconf:
Web based text editor for the configuration files
<pre>
pellmonconf -h
usage: pellmonconf [-h] [-P PORT] [-H HOST]

optional arguments:
  -h, --help            show this help message and exit
  -P PORT, --port PORT  Port number for webinterface, default 8083
  -H HOST, --host HOST  Host for webinterface, default 0.0.0.0
</pre>

### pellmon.conf
The default configuration is split up in several files in the conf.d directory using the directive `config_dir = /etc/pellmon/conf.d` in pellmon.conf.

## Deployment & Installation

### Docker Compose (Recommended)

The recommended deployment method is using **Docker Compose** on Linux. This isolates dependencies and handles inter-process D-Bus communication cleanly:

```bash
# Build the container image
docker compose build

# Start services in background (pellmonsrv and pellmonweb)
docker compose up -d

# View logs
docker compose logs -f

# Stop services
docker compose down
```

The `docker-compose.yml` environment:
- Runs `pellmonsrv` with an isolated session D-Bus bus over a shared volume socket (`/var/run/pellmon/bus_socket`).
- Healthcheck verifies `pellmonsrv` responsiveness using `dbus-send` peer ping.
- `pellmonweb` automatically waits for `pellmonsrv` to report healthy before starting (`service_healthy` condition).
- Data and logs are persisted to named Docker volumes (`pellmon-data`, `pellmon-logs`).
- Hardware access (serial converters `/dev/ttyUSB*`) is passed through with container privileges.

### Released images

Tagged releases are published automatically to Docker Hub as
`peterscholer74/pellmon:latest` and `peterscholer74/pellmon:{version}` for
`linux/amd64` and `linux/arm64`. `VERSION` at the repo root is the source of truth
for that tag. See [`RELEASING.md`](RELEASING.md) for the release process and its
one-time setup.

### Run from source (Linux):
```bash
# This prepares the project to run directly from the working directory
./autogen.sh
./configure --enable-debug
make
cd src
./pellmonsrv debug
# Run pellmonweb in another terminal
./pellmonweb
```

### System installation (Linux native):
```bash
# Add system users
sudo adduser --system --group --no-create-home pellmonsrv
sudo adduser --system --group --no-create-home pellmonweb
# Give the server access to the serial port
sudo adduser pellmonsrv dialout
# Create build system
./autogen.sh
# Configure for running as system users
./configure --with-user_srv=pellmonsrv --with-user_web=pellmonweb --sysconfdir=/etc
# Build PellMon
make
# Install PellMon
sudo make install
# Activate pellmon dbus system bus permissions
sudo service dbus reload
# Add them to init so they are started at boot
sudo update-rc.d pellmonsrv defaults
sudo update-rc.d pellmonweb defaults
# Start the daemons manually, or reboot
sudo service pellmonsrv start
sudo service pellmonweb start
```

#### Uninstall:
```bash
sudo make uninstall
# Remove from init if you added them
sudo update-rc.d pellmonsrv remove
sudo update-rc.d pellmonweb remove
```

## Web Authentication & Password Hashing

Pellmonweb supports secure password hashing with PBKDF2-HMAC-SHA256 (100,000 iterations).

To set or update user credentials in `config/pellmon.conf` under `[authentication]`:

```ini
[authentication]
username = admin
password = pbkdf2:sha256:100000$c2FsdHNhbHQ$d41d8cd98f00b204e9800998ecf8427e...
```

Generate a secure password hash with:
```bash
python3 -c "from Pellmonweb.auth import hash_password; print(hash_password('yourpassword'))"
```

*Breaking change:* plaintext passwords in `pellmon.conf` are no longer accepted and will fail to log in. Replace each password in `[authentication]` with the output of the `hash_password` one-liner above.

## Dependencies (Python 3)

### System packages (Debian/Ubuntu/Raspberry Pi OS):
```bash
sudo apt-get install \
    rrdtool \
    python3-rrdtool \
    python3-serial \
    python3-cherrypy3 \
    python3-dbus \
    python3-gi \
    python3-gi-cairo \
    gir1.2-glib-2.0 \
    python3-mako \
    python3-simplejson \
    python3-dateutil \
    python3-argcomplete
```

Or install Python dependencies via pip:
```bash
pip install -r requirements.txt
```

### Optional dependencies:
- `ws4py`: WebSocket support for real-time web UI updates.

### Additional dependencies for plugins:
- **OWFS**: `pyownet`
- **NBEcom**: `pycryptodome`, `xtea`
- **Openweathermap**: `pyowm`

### Build dependencies:
- `autoconf`
- `automake`
- `pkg-config`
