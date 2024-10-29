from mininet.topo import Topo
from mininet.net import Mininet
from mininet.link import TCLink
from mininet.node import RemoteController
from mininet.cli import CLI
from mininet.log import setLogLevel
import time
import hashlib
import os

class DumbbellTopo(Topo):    
    def build(self, delay_sw2_s2='50ms'):
        # Create hosts
        c1 = self.addHost('c1')
        c2 = self.addHost('c2')
        s1 = self.addHost('s1')
        s2 = self.addHost('s2')

        # Create switches
        sw1 = self.addSwitch('sw1')
        sw2 = self.addSwitch('sw2')

        # Add links with specified parameters
        self.addLink(c1, sw1, delay='5ms')
        self.addLink(c2, sw1, delay='5ms')
        self.addLink(s1, sw2, delay='5ms')

        buffer_size = 500
        # Link between sw1 and sw2 (bottleneck link)
        self.addLink(sw1, sw2, bw=100, delay='5ms', max_queue_size=buffer_size, use_htb=True, r2q=1000)
        
        # Link between sw2 and s2 with specified latency
        self.addLink(s2, sw2, delay=delay_sw2_s2, use_htb=True, r2q=1000)

def jain_fairness_index(allocations):
    n = len(allocations)
    sum_of_allocations = sum(allocations)
    sum_of_squares = sum(x ** 2 for x in allocations)
    
    jfi = (sum_of_allocations ** 2) / (n * sum_of_squares)
    return jfi

def run():
    setLogLevel('info')
    
    # Fixed parameters
    controller_ip = '127.0.0.1'
    controller_port = 6653
    SERVER_IP1 = "10.0.0.3"
    SERVER_PORT1 = 6555
    SERVER_IP2 = "10.0.0.4"
    SERVER_PORT2 = 6556
    DELAY = 50  # Fixed delay value for testing

    # Clean up any existing Mininet instance
    os.system("mn -c")
    print(f"\n--- Running topology with {DELAY}ms delay ---")

    # Create and start network
    topo = DumbbellTopo(delay_sw2_s2=f"{DELAY}ms")
    net = Mininet(topo=topo, link=TCLink, controller=None)
    net.addController(RemoteController('c0', ip=controller_ip, port=controller_port))
    net.start()

    # Get host references
    c1 = net.get('c1')
    c2 = net.get('c2')
    s1 = net.get('s1')
    s2 = net.get('s2')
    
    # Start servers and clients
    s1.cmd(f"python3 p2_server.py {SERVER_IP1} {SERVER_PORT1} &")
    s2.cmd(f"python3 p2_server.py {SERVER_IP2} {SERVER_PORT2} &")
    time.sleep(1)  # Wait for servers to start

    print("Starting clients...")
    # Record start times and start clients
    start_time_c1 = time.time()
    c1.cmd(f"python3 p2_client.py {SERVER_IP1} {SERVER_PORT1} --pref_outfile 1 > c1.log 2>&1 &")
    
    start_time_c2 = time.time()
    c2.cmd(f"python3 p2_client.py {SERVER_IP2} {SERVER_PORT2} --pref_outfile 2 > c2.log 2>&1 &")

    print("Waiting for transfers to complete...")
    # Monitor the transfer progress
    timeout = 60  # 60 seconds timeout
    duration_c1 = None
    duration_c2 = None
    
    while time.time() - start_time_c1 < timeout:
        current_time = time.time()
        # Check if client processes are still running
        c1_running = c1.cmd("pgrep -f 'p2_client.py'").strip()
        c2_running = c2.cmd("pgrep -f 'p2_client.py'").strip()
        
        # Record completion times when processes finish
        if not c1_running and duration_c1 is None:
            duration_c1 = current_time - start_time_c1
            print(f"Client 1 finished in {duration_c1:.2f} seconds")
            
        if not c2_running and duration_c2 is None:
            duration_c2 = current_time - start_time_c2
            print(f"Client 2 finished in {duration_c2:.2f} seconds")
        
        if duration_c1 is not None and duration_c2 is not None:
            print("All transfers completed!")
            break
            
        time.sleep(1)
    else:
        print("Timeout reached!")
        # If a client didn't finish, use timeout as its duration
        if duration_c1 is None:
            duration_c1 = timeout
        if duration_c2 is None:
            duration_c2 = timeout

    # Calculate JFI based on completion times
    if duration_c1 and duration_c2:
        inv_duration_c1 = 1.0 / duration_c1
        inv_duration_c2 = 1.0 / duration_c2
        jfi = jain_fairness_index([inv_duration_c1, inv_duration_c2])
        
        print("\n=== Results ===")
        print(f"Duration C1: {duration_c1:.2f} seconds")
        print(f"Duration C2: {duration_c2:.2f} seconds")
        print(f"Jain's Fairness Index: {jfi:.4f}")
    
    # Stop the network
    net.stop()

    print("\n--- Test completed ---")
    print("Check 1received_file.txt and 2received_file.txt for results")

if __name__ == "__main__":
    run()
