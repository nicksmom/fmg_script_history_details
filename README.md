# fmg_script_history_details
Extract details from FortiManager's script execution history and export to Excel file.
This script will poll the flatui_proxy (GUI API) and extract some details out of the JSON response, then dump those results to an Excel file.
* Adapt "parse_script_history" & "save_to_excel" functions for your specific use-case. Currently, the script extracts "rtc_date" & "rtc_time" from the output of "fnsysctl cat /proc/driver/rtc" after script has been executed on FortiGate(s) *

# Requirements
`pip3 install openpyxl`

# Set environment variables (optional)
```
export FMG_IP=10.224.129.21
export FMG_USER=admin
export FMG_PASS=password
export FMG_ADOM=root
export FMG_PLATFORM=FortiGate-VM64
export FMG_SCRIPT=cat_rtc
```

# Example command (without environment variables):
`python3 script_history_details.py --fmg 10.224.129.21 --user admin --password password --adom root --platform FortiGate-VM64 --script cat_rtc`


# Example command (user-specified input, without environment variables)
**user@host$** python3 script_history_details.py  
**FortiManager IP/FQDN:** 10.224.129.21  
**FortiManager Username:** admin  
**FortiManager Password:**  
**ADOM:** root  
**Desired platform (FortiGate-VM64, FortiGate-60F, FortiGate-100F):** FortiGate-VM64  
**Script name:** cat_rtc  
