import socket
import argparse
import json

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
    print("Sent START signal to server")

    with open(output_file_path, 'wb') as file:
        while True:
            try:
                # Receive the packet
                packet, _ = client_socket.recvfrom(MSS + 1000)  # Allow room for headers
                
                packet_data = json.loads(packet.decode())
                
                if 'end' in packet_data and packet_data['end']:
                    print("Received END signal from server, file transfer complete")
                    break
                
                seq_num = packet_data['seq']
                data = packet_data['data'].encode()

                # If the packet is in order, write it to the file
                if seq_num == expected_seq_num:
                    file.write(data)
                    print(f"Received packet {seq_num}, writing to file")
                    expected_seq_num += 1
                    
                    # Write any consecutive packets from the buffer
                    while expected_seq_num in buffer:
                        file.write(buffer[expected_seq_num])
                        print(f"Writing buffered packet {expected_seq_num}")
                        expected_seq_num += 1
                        del buffer[expected_seq_num-1]
                    
                    # Send cumulative ACK for the received packet
                    send_ack(client_socket, server_address, expected_seq_num)
                elif seq_num > expected_seq_num:
                    # Out of order packet, store in buffer
                    buffer[seq_num] = data
                    print(f"Received out of order packet {seq_num}, buffering")
                    send_ack(client_socket, server_address, expected_seq_num)
                else:
                    # Duplicate or old packet, send ACK again
                    send_ack(client_socket, server_address, expected_seq_num)
            except socket.timeout:
                print("Timeout waiting for data")
                send_ack(client_socket, server_address, expected_seq_num)

def send_ack(client_socket, server_address, seq_num):
    """
    Send a cumulative acknowledgment for the received packet.
    """
    ack_packet = json.dumps({'ack': seq_num}).encode()
    client_socket.sendto(ack_packet, server_address)
    print(f"Sent cumulative ACK for packet {seq_num}")

# Parse command-line arguments
parser = argparse.ArgumentParser(description='Reliable file receiver over UDP.')
parser.add_argument('server_ip', help='IP address of the server')
parser.add_argument('server_port', type=int, help='Port number of the server')
parser.add_argument('--pref_outfile', default='', help='Prefix for the output file')

args = parser.parse_args()
print(args.pref_outfile)

# Run the client
receive_file(args.server_ip, args.server_port, args.pref_outfile)