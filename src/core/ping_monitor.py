import time
import threading
import socket
from ping3 import ping
import logging
from src.utils.queue_operations import SafeQueue
from src.models.config_schema import ConfigSchema
from src.classes.enums import PublishType, SeverityLevel
from collections import OrderedDict
import subprocess
import datetime
import ipaddress

class PingMonitor:
    def __init__(self, config: ConfigSchema, queue: SafeQueue):
        self.config = config
        self.queue = queue
        self.logger = logging.getLogger(__name__)
        self.device_states = {}
        self.hostname_cache = {}
        self.hostname_update_counter = {}
        self.lock = threading.Lock()
        self.hostname_update_interval = 10 
        self.sorted_devices = sorted(self.config.devices, key=lambda d: ipaddress.ip_address(d.ip))

    def ping_device(self, device):
        for attempt in range(self.config.monitor.retry_attempts):
            try:
                result = ping(device.ip, timeout=2)
                if result is not None:
                    return True
                time.sleep(self.config.monitor.retry_interval)
            except Exception as e:
                self.logger.error(f"Error pinging {device.ip}: {str(e)}")
        return False

    def get_hostname(self, ip):
        with self.lock:
            if ip in self.hostname_cache:
                self.hostname_update_counter[ip] += 1
                if self.hostname_update_counter[ip] >= self.hostname_update_interval:
                    self.hostname_cache[ip] = self.resolve_hostname(ip)
                    self.hostname_update_counter[ip] = 0
                return self.hostname_cache[ip]
            else:
                hostname = self.resolve_hostname(ip)
                self.hostname_cache[ip] = hostname
                self.hostname_update_counter[ip] = 0
                return hostname

    def resolve_hostname(self, ip):
        hostname = self.get_hostname_dns(ip)
        if hostname == "Unknown":
            hostname = self.get_hostname_netbios(ip)
        if hostname == "Unknown":
            hostname = self.get_hostname_nmap(ip)
        return hostname

    def get_hostname_dns(self, ip):
        try:
            return socket.gethostbyaddr(ip)[0]
        except socket.herror:
            return "Unknown"

    def get_hostname_netbios(self, ip):
        try:
            import nmb.NetBIOS
            nb = nmb.NetBIOS.NetBIOS()
            result = nb.queryIPForName(ip)
            return result[0] if result else "Unknown"
        except Exception:
            return "Unknown"

    def get_hostname_nmap(self, ip):
        try:
            result = subprocess.run(['nmap', '-sn', '-oG', '-', ip], capture_output=True, text=True)
            for line in result.stdout.split('\n'):
                if 'Host:' in line and 'Status: Up' in line:
                    parts = line.split()
                    if len(parts) > 2:
                        return parts[2].strip('()')
            return "Unknown"
        except Exception:
            return "Unknown"

    def monitor_device(self, device, shutdown_flag):
        while not shutdown_flag.is_set():
            hostname = self.get_hostname(device.ip)
            is_responsive = self.ping_device(device)
            self.process_device_state(device, is_responsive, hostname)
            time.sleep(self.config.monitor.iteration_interval)

    def process_device_state(self, device, is_responsive, hostname):
        with self.lock:
            previous_state = self.device_states.get(device.ip)
            if previous_state is None or previous_state != is_responsive:
                self.device_states[device.ip] = is_responsive
                self.queue_message(device, is_responsive, hostname)
    
    def get_subnet(self, ip):
        try:
            ip_obj = ipaddress.IPv4Address(ip)
            network = ipaddress.IPv4Network(f"{ip}/24", strict=False)
            
            subnet_parts = str(network.network_address).split('.')[:3]
            
            subnet_parts.append('X')
            
            return '.'.join(subnet_parts)
        except ValueError:
            self.logger.error(f"Invalid IP address: {ip}")
            return "Unknown"

    def queue_message(self, device, is_responsive, hostname):
        severity = SeverityLevel.NOTIFICACION if is_responsive else SeverityLevel.MEDIO
        subnet = self.get_subnet(device.ip)
        message = OrderedDict([
            ("ID_Cliente", self.config.client.id_client),
            ("ID_SBC", self.config.client.id_sbc),
            ("IP", device.ip),
            ("Subnet", subnet),
            ("Nombre", device.name),
            ("Hostname", hostname),
            ("Mensaje", is_responsive),
            ("Tipo", "Evento"),
            ("Nivel_Severidad", severity.value),
            ("Fecha", datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f"))
        ])
        self.queue.put((PublishType.EVENTO, message))
        self.logger.info(f"Device {device.name} ({device.ip}, {hostname}) state changed to {'responsive' if is_responsive else 'unresponsive'}")

    def run(self, shutdown_flag):
        self.logger.info("Starting network monitoring...")
        threads = []
        for device in self.sorted_devices:
            thread = threading.Thread(target=self.monitor_device, args=(device, shutdown_flag))
            thread.start()
            threads.append(thread)

        # Wait for all threads to complete
        for thread in threads:
            thread.join()

        self.logger.info("Network monitoring stopped.")