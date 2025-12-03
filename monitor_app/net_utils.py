import netifaces
from typing import Optional


def get_interface_ip(interface: str) -> Optional[str]:
    try:
        iface_info = netifaces.ifaddresses(interface)
        inet_info = iface_info.get(netifaces.AF_INET)
        if not inet_info:
            return None
        return inet_info[0].get("addr")
    except ValueError:
        return None
