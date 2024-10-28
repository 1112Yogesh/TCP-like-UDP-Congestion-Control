import socket
import time
import argparse
import json
import math

# Constants
MSS = 1400  # Maximum Segment Size for each packet
INITIAL_CWND = 1  # Initial congestion window size (in segments)
INITIAL_SSTHRESH = 64  # Initial slow start threshold (in segments)
DUP_ACK_THRESHOLD = 3  # Threshold for duplicate ACKs to trigger fast recovery
FILE_PATH = "file_to_send.txt"
INITIAL_TIMEOUT = 1.0  # Initial timeout value

class CongestionControl:
    def __init__(self):
        self.cwnd = INITIAL_CWND
        self.ssthresh = INITIAL_SSTHRESH
        self.state = "slow_start"
        self.dup_ack_count = 0

    def on_ack_received(self, is_duplicate):
        if self.state == "slow_start":
            if not is_duplicate:
                self.cwnd += 1
                if self.cwnd >= self.ssthresh:
                    self.state = "congestion_avoidance"
            else:
                self.dup_ack_count += 1
                if self.dup_ack_count == DUP_ACK_THRESHOLD:
                    self.on_triple_duplicate_ack()
        elif self.state == "congestion_avoidance":
            if not is_duplicate:
                self.cwnd += 1 / self.cwnd
            else:
                self.dup_ack_count += 1
                if self.dup_ack_count == DUP_ACK_THRESHOLD:
                    self.on_triple_duplicate_ack()
        elif self.state == "fast_recovery":
            if not is_duplicate:
                self.cwnd = self.ssthresh
                self.dup_ack_count = 0
                self.state = "congestion_avoidance"
            else:
                self.cwnd += 1

    def on_triple_duplicate_ack(self):
        self.ssthresh = max(self.cwnd // 2, 2)
        self.cwnd = self.ssthresh + 3
        self.state = "fast_recovery"

    def on_timeout(self):
        self.ssthresh = max(self.cwnd // 2, 2)
        self.cwnd = INITIAL_CWND
        self.state = "slow_start"
        self.dup_ack_count = 0

def send_file(server_ip, server_port):
    """
    Send a predefined file to the client, ensuring reliability over UDP.
    """
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    server_socket.bind((server_ip, server_port))

    print(f"Server listening on {server_ip}:{server_port}")

    client_address = None
    file_path = FILE_PATH

    cc = CongestionControl()

    with open(file_path, 'rb') as file:
        seq_num = 0
        window_base = 0
        unacked_packets = {}
        last_ack_received = -1
        rtt_estimator = RTTEstimator()

        while True:
            while len(unacked_packets) < cc.cwnd:
                chunk = file.read(MSS)
                if not chunk:
                    break

                packet = create_packet(seq_num, chunk)
                if client_address:
                    server_socket.sendto(packet, client_address)
                else:
                    print("Waiting for client connection...")
                    data, client_address = server_socket.recvfrom(1024)
                    print(f"Connection established with client {client_address}")
                    server_socket.sendto(packet, client_address)

                unacked_packets[seq_num] = (packet, time.time())
                print(f"Sent packet {seq_num}, cwnd: {cc.cwnd:.2f}, state: {cc.state}")
                seq_num += 1

            try:
                server_socket.settimeout(rtt_estimator.timeout)
                ack_packet, _ = server_socket.recvfrom(1024)
                ack_data = json.loads(ack_packet.decode())
                ack_seq_num = ack_data['ack']

                if ack_seq_num > last_ack_received:
                    print(f"Received new ACK for packet {ack_seq_num}")
                    rtt_estimator.update(time.time() - unacked_packets[window_base][1])
                    last_ack_received = ack_seq_num
                    window_base = ack_seq_num
                    
                    # Remove acknowledged packets from the buffer
                    unacked_packets = {k: v for k, v in unacked_packets.items() if k >= window_base}
                    
                    cc.on_ack_received(is_duplicate=False)
                else:
                    print(f"Received duplicate ACK for packet {ack_seq_num}")
                    cc.on_ack_received(is_duplicate=True)

                    if cc.state == "fast_recovery" and cc.dup_ack_count >= DUP_ACK_THRESHOLD:
                        fast_recovery(server_socket, client_address, unacked_packets, window_base)

            except socket.timeout:
                print("Timeout occurred, retransmitting unacknowledged packets")
                cc.on_timeout()
                retransmit_unacked_packets(server_socket, client_address, unacked_packets)

            if not chunk and len(unacked_packets) == 0:
                print("File transfer complete")
                server_socket.sendto(json.dumps({'end': True}).encode(), client_address)
                break

def create_packet(seq_num, data):
    """
    Create a packet with the sequence number and data.
    """
    packet = {
        'seq': seq_num,
        'length': len(data),
        'data': data.decode()
    }
    return json.dumps(packet).encode()

def retransmit_unacked_packets(server_socket, client_address, unacked_packets):
    """
    Retransmit all unacknowledged packets.
    """
    for seq_num, (packet, _) in unacked_packets.items():
        server_socket.sendto(packet, client_address)
        print(f"Retransmitted packet {seq_num}")

def fast_recovery(server_socket, client_address, unacked_packets, window_base):
    """
    Retransmit the earliest unacknowledged packet (fast recovery).
    """
    if window_base in unacked_packets:
        server_socket.sendto(unacked_packets[window_base][0], client_address)
        print(f"Fast recovery: Retransmitted packet {window_base}")

class RTTEstimator:
    #  lec 24
    def __init__(self):
        self.srtt = None
        self.rttvar = None
        self.timeout = INITIAL_TIMEOUT

    def update(self, rtt):
        if self.srtt is None:
            self.srtt = rtt
            self.rttvar = rtt / 2
        else:
            self.rttvar = 0.75 * self.rttvar + 0.25 * abs(self.srtt - rtt)
            self.srtt = 0.875 * self.srtt + 0.125 * rtt
        self.timeout = self.srtt + 4 * self.rttvar

# Parse command-line arguments
parser = argparse.ArgumentParser(description='Reliable file transfer server over UDP with TCP Reno congestion control.')
parser.add_argument('server_ip', help='IP address of the server')
parser.add_argument('server_port', type=int, help='Port number of the server')

args = parser.parse_args()

# Run the server
send_file(args.server_ip, args.server_port)
