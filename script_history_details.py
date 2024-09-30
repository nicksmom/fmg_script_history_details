import json
import getpass
import openpyxl
from openpyxl import Workbook
import urllib3
import argparse
import os
import requests
from datetime import datetime
import logging

# Disable insecure HTTPS warnings
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

def parse_arguments():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description='Collect FortiGate script history from FortiManager.')
    
    parser.add_argument('--fmg', type=str, help='FortiManager IP/FQDN', required=False)
    parser.add_argument('--user', type=str, help='FortiManager Username', required=False)
    parser.add_argument('--password', type=str, help='FortiManager Password', required=False)  # Changed from --pass to --password
    parser.add_argument('--adom', type=str, help='ADOM', required=False)
    parser.add_argument('--platform', type=str, help='Desired platform (FortiGate-VM64, FortiGate-60F, FortiGate-100F)', required=False)
    parser.add_argument('--script', type=str, help='Script name', required=False)
    parser.add_argument('--verbose', '-v', action='store_true', help='Enable verbose mode')
    
    return parser.parse_args()

def configure_logging(verbose):
    """Configure logging based on verbosity flag."""
    if verbose:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.INFO)

def get_input_parameters(args):
    """Get input parameters from environment variables, command line arguments, or prompt the user."""
    fmg_ip = args.fmg or os.getenv('FMG_IP') or input("FortiManager IP/FQDN: ")
    user = args.user or os.getenv('FMG_USER') or input("FortiManager Username: ")
    passwd = args.password or os.getenv('FMG_PASS') or getpass.getpass("FortiManager Password: ")  # Changed args.pass to args.password
    adom = args.adom or os.getenv('FMG_ADOM') or input("ADOM: ")
    platform = args.platform or os.getenv('FMG_PLATFORM') or input("Desired platform (FortiGate-VM64, FortiGate-60F, FortiGate-100F): ")
    script_name = args.script or os.getenv('FMG_SCRIPT') or input("Script name: ")
    
    return fmg_ip, user, passwd, adom, platform, script_name

def login_fmg(fmg_ip, user, passwd):
    """First authentication to obtain session token."""
    auth_url = f"https://{fmg_ip}/jsonrpc"
    headers = {'Content-Type': 'application/json'}
    payload = {
        "id": 1,
        "method": "exec",
        "params": [{
            "data": [{"passwd": passwd, "user": user}],
            "url": "sys/login/user"
        }],
        "session": None,
        "verbose": 1
    }

    logging.debug(f"Request to {auth_url}: {json.dumps(payload)}")
    response = requests.post(auth_url, json=payload, headers=headers, verify=False)
    result = response.json()
    logging.debug(f"Response from {auth_url}: {result}")

    if result["result"][0]["status"]["code"] == 0:
        session = result["session"]
        # Perform second authentication immediately after the first one
        cookies = login_fmg_flatui(fmg_ip, user, passwd)
        return session, cookies
    else:
        raise Exception("First authentication failed")

def login_fmg_flatui(fmg_ip, user, passwd):
    """Second authentication to obtain CURRENT_SESSION and HTTP_CSRF_TOKEN cookies."""
    auth_url = f"https://{fmg_ip}/cgi-bin/module/flatui_auth"
    headers = {'Content-Type': 'application/json'}
    payload = {
        "url": "/gui/userauth",
        "method": "login",
        "params": {
            "username": user,
            "secretkey": passwd,
            "logintype": 0
        }
    }

    logging.debug(f"Request to {auth_url}: {json.dumps(payload)}")
    response = requests.post(auth_url, json=payload, headers=headers, verify=False)
    logging.debug(f"Response from {auth_url}: {response.cookies}")

    if response.status_code == 200:
        cookies = response.cookies
        return cookies
    else:
        raise Exception("Second authentication failed")

def get_device_list(fmg_ip, session, adom, platform):
    """Get the list of devices from FortiManager."""
    api_url = f"https://{fmg_ip}/jsonrpc"
    headers = {'Content-Type': 'application/json'}
    payload = {
        "method": "get",
        "params": [{
            "loadsub": 0,
            "url": f"/dvmdb/adom/{adom}/device",
            "fields": ["sn", "hostname"],
            "filter": [["platform_str", "==", platform]]
        }],
        "session": session,
        "id": 1
    }

    logging.debug(f"Request to {api_url}: {json.dumps(payload)}")
    response = requests.post(api_url, json=payload, headers=headers, verify=False)
    logging.debug(f"Response from {api_url}: {response.json()}")

    result = response.json()
    if "result" in result and result["result"] and "data" in result["result"][0]:
        return result["result"][0]["data"]
    else:
        raise Exception("Failed to retrieve device list or no devices found")

def get_script_history(fmg_ip, hostname, session, cookies):
    """Get script execution history for a device."""
    api_url = f"https://{fmg_ip}/cgi-bin/module/flatui_proxy"
    payload = {
        "url": "/gui/adom/dvm/task",
        "method": "get",
        "params": {
            "deviceName": hostname,
            "adomName": "root"
        }
    }

    logging.debug(f"Request to {api_url}: {json.dumps(payload)}")
    response = requests.post(api_url, json=payload, cookies=cookies, verify=False)
    logging.debug(f"Response from {api_url}: {response.json()}")

    return response.json()

def parse_script_history(history, script_name):
    """Parse the script history and return the desired output."""
    # Ensure the history result contains data and it's in the expected format
    if "result" not in history or not history["result"] or "data" not in history["result"][0]:
        print(f"No script history found for {script_name}")
        return None, None, None

    for entry in history["result"][0]["data"]:
        # Check if the entry matches the desired script name
        if entry.get("script_name") == script_name:
            content = entry.get("content", "")
            
            # Find hostname: extract between "Starting log (Run on device)\n\n" and the next "  "
            start_marker = "Starting log (Run on device)\n\n"
            if start_marker in content:
                start_index = content.find(start_marker) + len(start_marker)
                end_index = content.find("  ", start_index)
                hostname = content[start_index:end_index].strip()
            else:
                hostname = "Unknown"

            # Extract rtc_time and rtc_date
            rtc_time = ""
            rtc_date = ""
            lines = content.split("\n")
            for line in lines:
                if "rtc_time" in line:
                    rtc_time = line.split(":")[1].strip() + ":" + line.split(":")[2].strip() + ":" + line.split(":")[3].strip()
                if "rtc_date" in line:
                    rtc_date = line.split(":")[1].strip()

            return hostname, rtc_time, rtc_date

    return None, None, None

def save_to_excel(data, filename_prefix):
    """Save parsed data to an Excel file with UTC timestamp in the filename."""
    utc_suffix = datetime.utcnow().strftime('%m%d%y_%H%M%S')
    filename = f"{filename_prefix}_{utc_suffix}.xlsx"
    
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(["Hostname", "SN", "rtc_time", "rtc_date"])

    for row in data:
        sheet.append(row)

    workbook.save(filename)
    print(f"Data has been saved to {filename}")

def main():
    args = parse_arguments()
    configure_logging(args.verbose)
    
    fmg_ip, user, passwd, adom, platform, script_name = get_input_parameters(args)
    
    try:
        # First and second authentication (session and cookies are obtained here)
        session, cookies = login_fmg(fmg_ip, user, passwd)

        # Fetch the list of devices
        device_list = get_device_list(fmg_ip, session, adom, platform)

        parsed_data = []
        for device in device_list:
            hostname = device['hostname']
            sn = device['sn']
            script_history = get_script_history(fmg_ip, hostname, session, cookies)
            parsed_result = parse_script_history(script_history, script_name)

            if parsed_result[0]:  # If parsing was successful
                parsed_data.append([parsed_result[0], sn, parsed_result[1], parsed_result[2]])

        # Save the parsed data to an Excel file
        save_to_excel(parsed_data, 'fortigate_script_history')

    except Exception as e:
        print(f"An error occurred: {e}")

if __name__ == "__main__":
    main()
