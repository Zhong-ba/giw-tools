import argparse
import os

import uvicorn


def main() -> None:
    parser = argparse.ArgumentParser(description='Run the Genshin Wiki Workshop.')
    parser.add_argument('--port', type=int, default=int(os.environ.get('PORT', 8000)))
    parser.add_argument('--host', default='127.0.0.1', help='Use 0.0.0.0 to accept connections from other machines.')
    parser.add_argument('--hosted', action='store_true',
                        help='Serve many anonymous users: no dataset setup or bot, and browsers keep their own jobs.')
    args = parser.parse_args()
    if args.hosted:
        os.environ['PAINMELO_HOSTED'] = '1'
    uvicorn.run('webui.app:app', host=args.host, port=args.port, proxy_headers=args.hosted)


if __name__ == '__main__':
    main()
