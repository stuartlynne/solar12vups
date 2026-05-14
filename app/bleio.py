import multiprocessing
import json
import queue
import sys
import time


SENTINEL = ("__BLE_IO_STOP__", None)


def _merge_device_payload(existing, incoming):
    if existing is None:
        return incoming
    if not isinstance(existing, dict) or not isinstance(incoming, dict):
        return incoming
    merged = dict(existing)
    merged.update(incoming)
    return merged


def ble_data_io_worker(input_queue, output_queue, stop_event, flush_interval=0.1):
    pending = {}
    last_flush = time.monotonic()

    def flush():
        nonlocal last_flush
        if not pending:
            return
        for device_name, data in pending.items():
            output_queue.put((device_name, data))
        pending.clear()
        last_flush = time.monotonic()

    def is_ui_event(data):
        return isinstance(data, dict) and '__ui_event__' in data

    while not stop_event.is_set():
        timeout = max(0.01, flush_interval - (time.monotonic() - last_flush))
        item = None
        try:
            item = input_queue.get(timeout=timeout)
        except queue.Empty:
            flush()
            continue

        if item == SENTINEL:
            break
        if item is None:
            continue

        device_name, data = item
        if is_ui_event(data):
            flush()
            output_queue.put((device_name, data))
            last_flush = time.monotonic()
            continue
        pending[device_name] = _merge_device_payload(pending.get(device_name), data)

        while True:
            try:
                next_item = input_queue.get_nowait()
            except queue.Empty:
                break

            if next_item == SENTINEL:
                stop_event.set()
                break
            if next_item is None:
                continue

            next_device_name, next_data = next_item
            if is_ui_event(next_data):
                flush()
                output_queue.put((next_device_name, next_data))
                last_flush = time.monotonic()
                continue
            pending[next_device_name] = _merge_device_payload(pending.get(next_device_name), next_data)

        if time.monotonic() - last_flush >= flush_interval:
            flush()

    flush()


def start_ble_data_io_process():
    ctx = multiprocessing.get_context("spawn")
    input_queue = ctx.Queue()
    output_queue = ctx.Queue()
    stop_event = ctx.Event()
    process = ctx.Process(
        target=ble_data_io_worker,
        args=(input_queue, output_queue, stop_event),
        name="BLEDataIO",
        daemon=True,
    )
    process.start()
    return process, input_queue, output_queue, stop_event


def stop_ble_data_io_process(process, input_queue, stop_event):
    if process is None:
        return
    try:
        stop_event.set()
    except Exception:
        pass
    try:
        input_queue.put_nowait(SENTINEL)
    except Exception:
        pass
    process.join(timeout=5)
    if process.is_alive():
        process.terminate()
        process.join(timeout=2)


def _enqueue_stdin_payload(input_queue, payload):
    if not isinstance(payload, dict):
        return

    if 'device_name' in payload and 'data' in payload:
        input_queue.put((payload['device_name'], payload['data']))
        return

    if 'devices' in payload and isinstance(payload['devices'], list):
        for device in payload['devices']:
            if not isinstance(device, dict):
                continue
            name = device.get('name')
            if not name:
                continue
            input_queue.put((name, {'__scan__': (None, device, False)}))
        return

    name = payload.get('name') or payload.get('device_name')
    if name:
        input_queue.put((name, payload))


def main():
    process, input_queue, output_queue, stop_event = start_ble_data_io_process()
    try:
        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError as e:
                print(json.dumps({'error': f'invalid json: {e}', 'line': line}), file=sys.stderr, flush=True)
                continue
            _enqueue_stdin_payload(input_queue, payload)

            while True:
                try:
                    device_name, data = output_queue.get_nowait()
                except queue.Empty:
                    break
                print(json.dumps({'device_name': device_name, 'data': data}), file=sys.stderr, flush=True)
    except KeyboardInterrupt:
        pass
    finally:
        try:
            input_queue.put_nowait(SENTINEL)
        except Exception:
            pass
        deadline = time.monotonic() + 1.0
        while time.monotonic() < deadline:
            try:
                device_name, data = output_queue.get(timeout=0.1)
            except queue.Empty:
                continue
            print(json.dumps({'device_name': device_name, 'data': data}), file=sys.stderr, flush=True)
        stop_ble_data_io_process(process, input_queue, stop_event)


if __name__ == "__main__":
    main()
