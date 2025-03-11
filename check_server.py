import asyncio
import logging
import argparse
from aioquic.asyncio import connect, serve
from aioquic.asyncio.protocol import QuicConnectionProtocol
from aioquic.quic.configuration import QuicConfiguration
from aioquic.quic.events import HandshakeCompleted, ProtocolNegotiated    
from aioquic.asyncio import connect, QuicConnectionProtocol
from aioquic.h3.events import WebTransportStreamDataReceived
from aioquic.h3.connection import H3_ALPN, H3Connection
from aioquic.h3.events import (
    H3Event,
    HeadersReceived,
    WebTransportStreamDataReceived,
)
from typing import Optional

logging.basicConfig(level=logging.INFO)

# Server Implementation
class WebTransportServerProtocol(QuicConnectionProtocol):
    """ Serrver initiates data transfer once client opens a WebTransport stream"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.stream_id = None
        self._http: Optional[H3Connection] = None
        self.hello_initiated=False

    async def helloworld(self, stream_id: int):
        """ Send message every 1 second """
        i = 0
        print(stream_id)
        while True:
            if not self.hello_initiated:
                self.hello_initiated=True
                self._quic.send_stream_data(stream_id, b"hellostream", False)
            else:
                self._quic.send_stream_data(stream_id, b"Hello", False)
                print('sending hello ', i)
                i+=1
            self.transmit()
            await asyncio.sleep(1)
    
    def http_event_received(self, event: H3Event):
        #print('HTTP received',event)
        if isinstance(event, WebTransportStreamDataReceived):
            print(f"Received: {event.data.decode().strip()}")
            data = event.data.decode().strip()
            if data == 'hellohere':
                asyncio.ensure_future(self.helloworld(event.stream_id)) #initate hello stream

        if isinstance(event, HeadersReceived):
            # Add logic to handle headers
            print(f"Received headers: {event.headers}")
    
    def quic_event_received(self, event):
        #print('QUIC received',event)
        if isinstance(event, ProtocolNegotiated):
            if event.alpn_protocol in H3_ALPN:
                print('creating h3 connection')
                self._http = H3Connection(self._quic, enable_webtransport=True)
        elif isinstance(event, HandshakeCompleted):
            logging.info("Handshake completed, ready for WebTransport session.")  
        elif self._http is not None:
            print('handling event')
            for http_event in self._http.handle_event(event):
                self.http_event_received(http_event) 

async def run_server(args):
    configuration = QuicConfiguration(is_client=False,alpn_protocols=H3_ALPN,max_datagram_frame_size=65536,)
    configuration.load_cert_chain(args.cert, args.key)
    await serve(args.host, args.port, configuration=configuration, create_protocol=WebTransportServerProtocol)
    await asyncio.Future()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="QUIC server")
    parser.add_argument(
        "--host", type=str, default="localhost", help="The host to listen on"
    )
    parser.add_argument(
        "--port", type=int, default=4433, help="The port to listen on"
    )
    parser.add_argument(
        "--cert", type=str, default="ssl_cert.pem", help="The certificate file"
    )
    parser.add_argument(
        "--key", type=str, default="ssl_key.pem", help="The private key file"
    )
    args = parser.parse_args()
    asyncio.run(run_server(args))