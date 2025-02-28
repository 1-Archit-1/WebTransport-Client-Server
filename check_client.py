import asyncio
import argparse
from aioquic.asyncio import connect
from aioquic.asyncio.protocol import QuicConnectionProtocol
from aioquic.quic.configuration import QuicConfiguration
from aioquic.quic.events import HandshakeCompleted,ProtocolNegotiated
from aioquic.h3.connection import H3_ALPN, H3Connection
from aioquic.asyncio import connect, QuicConnectionProtocol
from aioquic.h3.events import WebTransportStreamDataReceived
from aioquic.quic.logger import QuicFileLogger

class WebTransportClientProtocol(QuicConnectionProtocol):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.stream_id = None
        self.queue = asyncio.Queue()

    def make_session(self):
        """ Send headers and initiate WebTransport session """
        quic_client = self._http._quic
        stream_id = quic_client.get_next_available_stream_id()
        self._http.send_headers(
            stream_id=stream_id,
            headers=[
                (b":method", b"CONNECT"),
                (b":scheme", b"https"),
                (b":authority", b"localhost"),
                (b":path", b"/"),
                (b":protocol", b"webtransport"),
            ],
        )
        print('Sending headers')
        self.transmit()
        return stream_id 

    def quic_event_received(self, event):
        #print('QUIC received',event)
        if isinstance(event, ProtocolNegotiated):
            if event.alpn_protocol in H3_ALPN:
                print('creating h3 connection')
                self._http = H3Connection(self._quic, enable_webtransport=True)
        if isinstance(event, HandshakeCompleted):
            print("Client connected, opening stream.")
        if self._http is not None:
            for http_event in self._http.handle_event(event):
                self.http_event_received(http_event)

    def http_event_received(self, event):
        #print('HTTP received',event)
        if isinstance(event, WebTransportStreamDataReceived):
            if event.data.decode().strip() == 'hellostream':
                self.hellostream = event.stream_id
            else:
                self.queue.put_nowait(event.data)      

    async def output_response(self,stream_id):
        """ Output response from buffer"""
        while True:
            data = await self.queue.get()
            print(data)

async def create_webtransport_stream(protocol,session_id):
    """ Create WebTransport stream and to current context """
    stream_id = protocol._http.create_webtransport_stream(session_id)
    protocol.transmit()
    stream = protocol._http._get_or_create_stream(stream_id)
    stream.frame_type = 0x41
    stream.session_id = session_id
    return stream_id

async def helloworld(protocol,session_id):
    """ Initiate stream to receive data"""
    stream_id1 = await create_webtransport_stream(protocol,session_id)
    protocol._quic.send_stream_data(stream_id1, b"hellohere", False)
    protocol.transmit()
    await protocol.output_response(stream_id = stream_id1)

async def receive_media(protocol):
    session_id = protocol.make_session() 
    return session_id
    
async def start_client(args):
    configuration = QuicConfiguration(
        is_client=True,
        alpn_protocols=H3_ALPN,
        max_datagram_frame_size=65536,
    )

    #configuration.quic_logger = QuicFileLogger("client.log")
    configuration.load_verify_locations(args.cert)
    async with connect(args.host, args.port, configuration=configuration, create_protocol=WebTransportClientProtocol) as protocol:
        await protocol.wait_connected()
        session_id = await receive_media(protocol)
        await helloworld(protocol,session_id=session_id)
        await asyncio.sleep(20)
        
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="QUIC client")
    parser.add_argument(
        "--host", type=str, default="localhost", help="The host to connect to"
    )
    parser.add_argument(
        "--port", type=int, default=4433, help="The port to connect to"
    )
    parser.add_argument(
        "--cert", type=str, default="pycacert.pem", help="The certificate file"
    )
    args = parser.parse_args()
    loop = asyncio.get_event_loop()
    loop.run_until_complete(start_client(args))