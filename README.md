# CVE-2022-30075
Authenticated Remote Code Execution in Tp-Link Routers

### Affected Devices
If your Tp-Link router has backup and restore functionality and firmware is older than june 2022, it is probably vulnerable

### Tested With
Tp-Link Archer AX50, other tplink routers may use different format of backups and exploit needs to be modified

### PoC
Using exploit for starting telnet daemon on the router
![tplink](https://user-images.githubusercontent.com/28111712/172499966-8a5d486f-c79d-4fe2-95ff-de77d211ab54.png)

### Timeline
15.03.2022 - Identified vulnerability  
15.03.2022 - Contacted Tp-Link support  
16.03.2022 - Recieved response from Tp-Link  
02.05.2022 - Assigned CVE  
27.05.2022 - Tp-Link released firmware with fixed vulnerability  
07.06.2022 - Published technical details  
