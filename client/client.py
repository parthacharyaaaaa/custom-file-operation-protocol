import asyncio
from time import time
import orjson
from models.flags import CategoryFlag, AuthFlags, FileFlags
from models.request_model import BaseHeaderComponent, BaseAuthComponent, BaseFileComponent
from models.constants import RESPONSE_CONSTANTS


async def main():
    reader, writer = await asyncio.open_connection('127.0.0.1', 6000)
    request_auth: BaseAuthComponent = BaseAuthComponent(identity='TastyCupNoodles', password='TastyCumNoodles')
    auth_stream: bytes = request_auth.model_dump_json().encode('utf-8')
    request_header: BaseHeaderComponent = BaseHeaderComponent(version='0.0.1', auth_size=len(auth_stream), body_size=0,
                                                                sender_hostname='0.0.0.0', sender_port=1000, sender_timestamp=time(),
                                                                finish=False, category=CategoryFlag.AUTH.value,
                                                                subcategory=AuthFlags.LOGIN.value)

    request_stream: bytes = request_header.model_dump_json().encode('utf-8')
    request_stream += b' '*(256 - len(request_stream))
    writer.write(request_stream)
    writer.write(auth_stream)
    await writer.drain()

    data = await reader.readexactly(RESPONSE_CONSTANTS.header.bytesize)
    data_dict = orjson.loads(data)
    print('received: ', data_dict)
    auth_data = await reader.readexactly(data_dict['body_size'])
    auth_dict = orjson.loads(auth_data)
    print('auth:', auth_dict)

    # File req
    auth_stream = BaseAuthComponent(identity='TastyCupNoodles', token = auth_dict['contents']['token'], refresh_digest=auth_dict['contents']['refresh_digest']).model_dump_json().encode()
    file_component: BaseFileComponent = BaseFileComponent(subject_file='pp.txt', subject_file_owner='TastyCupNoodles', cursor_keepalive=False, write_data='SO MANY FIIIIIISH THERE IN THE SEAAAAAA I WANTED YOU YOU WANTED MEEEE TATS JUST A PHASE ITS GIT TO PASS I WAS A TRAIN MOVING TOO FAAAAAST')
    file_stream = file_component.model_dump_json().encode('utf-8')
    request_header2: BaseHeaderComponent = BaseHeaderComponent(version='0.0.1', auth_size=len(auth_stream), body_size=len(file_stream),
                                                                sender_hostname='0.0.0.0', sender_port=1000, sender_timestamp=time(),
                                                                finish=True, category=CategoryFlag.FILE_OP,
                                                                subcategory=FileFlags.WRITE)
    
    header_stream = request_header2.model_dump_json().encode()
    header_stream += b' ' * (256 - len(header_stream))
    print(header_stream)
    writer.write(header_stream)
    writer.write(auth_stream)
    writer.write(file_stream)
    await writer.drain()

    data = await reader.readexactly(RESPONSE_CONSTANTS.header.bytesize)
    data_dict = orjson.loads(data)
    print('File response', data_dict)

    writer.write_eof()
    await writer.drain()

    writer.close()
    await writer.wait_closed()

if __name__ == '__main__':
    asyncio.run(main())