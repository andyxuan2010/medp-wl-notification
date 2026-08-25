A simple python program can send you the notification of waiting list number in real time for the Quebec Med-P


### Support programs
1. Mcgill Med-P
2. UdeM Premed
3. UdeS Premed
   
### Not supported  
1. Laval University
2. University of Ottawa
3. UofT
   
### Notification methods
1. email
2. sms

### Deployment
cronjob on linux based VM
Possible to extend to Windows based or cloud based.

## Pipeline used

The repository's GitHub Pages workflow publishes static repository content on
`main`; it does not run the monitor or send notifications. The operational
pipeline is a scheduled Linux process installed by `monitor.sh`.

## Usage

Create a virtual environment, install `requirements.txt`, configure `.env` and
the recipients file, then test with:

```bash
python3 -m venv venv
. venv/bin/activate
pip install -r requirements.txt
python monitor.py
```

After confirming the email/SMS configuration, `./monitor.sh` installs the
dependencies and a ten-minute cron entry. Keep SMTP passwords and recipient
data out of Git, and monitor `monitor.log` and the cron output.



