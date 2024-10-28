import socket
import argparse
import json
import logging
import time
import os  # Add this import at the top with other imports

# Create logs directory if it doesn't exist
log_dir = 'logs'
os.makedirs(log_dir, exist_ok=True)

# Update log filename to use the logs directory
log_filename = os.path.join(log_dir, f'client_{time.strftime("%Y%m%d_%H%M%S")}.log')
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_filename)  # Log to timestamped file in logs directory
    ]
)

# Constants
MSS = 1400  # Maximum Segment Size

def receive_file(server_ip, server_port, pref_outfile):
    """
    Receive the file from the server with reliability, handling packet loss
    and reordering.
    """
    client_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    client_socket.settimeout(2)  # Set timeout for server response

    server_address = (server_ip, server_port)
    expected_seq_num = 0
    output_file_path = f"{pref_outfile}received_file.txt"  # Default file name
    buffer = {}

    # Send initial connection request to server
    client_socket.sendto(b"START", server_address)
    logging.info("Sent START signal to server")

    received_packets = set()  # Add this to track received packets

    # Add receiver window size
    receiver_window = 65535  # Standard TCP window size

    with open(output_file_path, 'wb') as file:
        while True:
            try:
                # Receive the packet
                packet, _ = client_socket.recvfrom(MSS + 1000)  # Allow room for headers
                
                packet_data = json.loads(packet.decode())
                
                if 'end' in packet_data and packet_data['end']:
                    logging.info("Received END signal from server, file transfer complete")
                    break
                
                seq_num = packet_data['seq']
                data = packet_data['data'].encode()

                if seq_num not in received_packets:  # Only process new packets
                    if seq_num == expected_seq_num:
                        file.write(data)
                        received_packets.add(seq_num)
                        logging.info(f"Received packet {seq_num}, writing to file")
                        expected_seq_num += 1
                        
                        # Write any consecutive packets from the buffer
                        while expected_seq_num in buffer:
                            file.write(buffer[expected_seq_num])
                            logging.info(f"Writing buffered packet {expected_seq_num}")
                            expected_seq_num += 1
                            del buffer[expected_seq_num-1]
                        
                        # Include receiver window in ACK
                        send_ack(client_socket, server_address, expected_seq_num, receiver_window)
                    elif seq_num > expected_seq_num:
                        # Out of order packet, store in buffer
                        buffer[seq_num] = data
                        logging.info(f"Received out of order packet {seq_num}, buffering")
                        send_ack(client_socket, server_address, expected_seq_num, receiver_window)
                    else:
                        # Duplicate or old packet, send ACK again
                        send_ack(client_socket, server_address, expected_seq_num, receiver_window)
            except socket.timeout:
                logging.info("Timeout waiting for data")
                send_ack(client_socket, server_address, expected_seq_num, receiver_window)

def send_ack(client_socket, server_address, seq_num, window_size):
    """
    Send a cumulative acknowledgment with receiver window size.
    """
    ack_packet = json.dumps({
        'ack': seq_num,
        'window': window_size
    }).encode()
    client_socket.sendto(ack_packet, server_address)
    logging.info(f"Sent ACK {seq_num} with window {window_size}")

# Parse command-line arguments
parser = argparse.ArgumentParser(description='Reliable file receiver over UDP.')
parser.add_argument('server_ip', help='IP address of the server')
parser.add_argument('server_port', type=int, help='Port number of the server')
parser.add_argument('--pref_outfile', default='', help='Prefix for the output file')

args = parser.parse_args()
logging.info(args.pref_outfile)

# Run the client
receive_file(args.server_ip, args.server_port, args.pref_outfile)
