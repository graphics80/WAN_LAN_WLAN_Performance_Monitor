import netifaces
from typing import Optional


def get_interface_ip(interface: str) -> Optional[str]:
    """Return the IPv4 address for a network interface, or None if unavailable."""
    try:
        iface_info = netifaces.ifaddresses(interface)
        inet_info = iface_info.get(netifaces.AF_INET)
        if not inet_info:
            return None
        return inet_info[0].get("addr")
    except ValueError:
        return None
