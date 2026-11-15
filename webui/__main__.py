import argparse

import uvicorn


def main() -> None:
    parser = argparse.ArgumentParser(description='Run the local Genshin Wiki Workshop.')
    parser.add_argument('--port', type=int, default=8000)
    args = parser.parse_args()
    uvicorn.run('webui.app:app', host='127.0.0.1', port=args.port)


if __name__ == '__main__':
    main()
