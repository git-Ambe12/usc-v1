import asyncio
import os
import threading
from datetime import datetime

from kivy.app import App
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.lang import Builder
from kivy.properties import (
    BooleanProperty, ColorProperty, NumericProperty, OptionProperty,
    StringProperty
)
from kivy.uix.behaviors import ButtonBehavior
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.modalview import ModalView
from kivy.utils import platform

from bleak import BleakScanner, BleakClient

from pdf_report import build_pdf


# BLE CONFIGURATION
# Shown as "Recommended" at the top of the scan list
DEVICE_NAME = "Basic BLE project"
SCAN_SECONDS = 10

# GPS: stop once a fix is this accurate (metres), or give up after GPS_TIMEOUT
GPS_GOOD_ACCURACY = 30
GPS_TIMEOUT = 30

# com.google.android.gms.location.Priority.PRIORITY_HIGH_ACCURACY
PRIORITY_HIGH_ACCURACY = 100

# Replace with your actual Service UUID if required
CHAR3_UUID = "0000fff3-0000-1000-8000-00805f9b34fb"
CHAR4_UUID = "0000fff4-0000-1000-8000-00805f9b34fb"

# The device rejects CHAR3 writes longer than this ("Invalid Attribute Value Length")
MAX_WRITE_BYTES = 20

# Friendly names for record keys sent by the device
KEY_LABELS = {
    "N": "Patient Name",
    "C": "City",
    "L": "Location",
    "T": "Device Time",
    "B": "Born Date",
    "BT": "Born Time",
    "U": "UC Cut Time",
}


KV = """
#:import dp kivy.metrics.dp

#:set C_PRIMARY (0.055, 0.486, 0.525, 1)
#:set C_DANGER (0.863, 0.149, 0.149, 1)
#:set C_BG (0.933, 0.949, 0.965, 1)
#:set C_TEXT (0.122, 0.161, 0.216, 1)
#:set C_MUTED (0.420, 0.447, 0.502, 1)
#:set C_FIELD (0.953, 0.957, 0.965, 1)
#:set C_BORDER (0.898, 0.906, 0.922, 1)

#:set STATE_DOT {"offline": (0.612, 0.639, 0.686, 1), "scanning": (0.984, 0.749, 0.141, 1), "connecting": (0.984, 0.749, 0.141, 1), "connected": (0.290, 0.871, 0.502, 1)}
#:set STATE_TEXT {"offline": "Offline", "scanning": "Scanning", "connecting": "Connecting", "connected": "Connected"}
#:set STATUS_FG {"info": (0.420, 0.447, 0.502, 1), "busy": (0.706, 0.325, 0.035, 1), "ok": (0.082, 0.502, 0.239, 1), "error": (0.725, 0.110, 0.110, 1)}
#:set STATUS_BG {"info": (0.953, 0.957, 0.965, 1), "busy": (0.996, 0.953, 0.780, 1), "ok": (0.863, 0.988, 0.906, 1), "error": (0.996, 0.886, 0.886, 1)}


<AppButton>:
    size_hint_y: None
    height: dp(50)
    bold: True
    font_size: "15sp"
    color: self.fg
    disabled_color: self.fg
    opacity: 0.45 if self.disabled else 1
    canvas.before:
        Color:
            rgba: (self.bg[0] * 0.85, self.bg[1] * 0.85, self.bg[2] * 0.85, 1) if self.state == "down" else self.bg
        RoundedRectangle:
            pos: self.pos
            size: self.size
            radius: [dp(12)]

<OutlineButton@AppButton>:
    bg: 1, 1, 1, 1
    fg: C_PRIMARY
    canvas.after:
        Color:
            rgba: self.fg
        Line:
            rounded_rectangle: (self.x + 1, self.y + 1, self.width - 2, self.height - 2, dp(12))
            width: 1.2

<Card@BoxLayout>:
    orientation: "vertical"
    size_hint_y: None
    height: self.minimum_height
    padding: dp(16)
    spacing: dp(12)
    canvas.before:
        Color:
            rgba: 0, 0, 0, 0.06
        RoundedRectangle:
            pos: self.x, self.y - dp(2)
            size: self.size
            radius: [dp(16)]
        Color:
            rgba: 1, 1, 1, 1
        RoundedRectangle:
            pos: self.pos
            size: self.size
            radius: [dp(16)]

<SectionTitle@Label>:
    color: C_TEXT
    bold: True
    font_size: "17sp"
    size_hint_y: None
    height: dp(28)
    text_size: self.size
    halign: "left"
    valign: "middle"

<FieldLabel@Label>:
    color: C_MUTED
    font_size: "13sp"
    size_hint_y: None
    height: dp(18)
    text_size: self.size
    halign: "left"
    valign: "middle"

<Field@TextInput>:
    multiline: False
    write_tab: False
    size_hint_y: None
    height: dp(48)
    font_size: "15sp"
    background_normal: ""
    background_active: ""
    background_color: 0, 0, 0, 0
    foreground_color: C_TEXT
    hint_text_color: C_MUTED
    cursor_color: C_PRIMARY
    padding: [dp(14), (self.height - self.line_height) / 2]
    canvas.before:
        Color:
            rgba: C_FIELD
        RoundedRectangle:
            pos: self.pos
            size: self.size
            radius: [dp(10)]
        Color:
            rgba: C_PRIMARY if self.focus else C_BORDER
        Line:
            rounded_rectangle: (self.x, self.y, self.width, self.height, dp(10))
            width: 1.4 if self.focus else 1
        # TextInput draws its text with the last color set here, so restore it
        Color:
            rgba: self.foreground_color if self.text else self.hint_text_color

<FieldGroup@BoxLayout>:
    orientation: "vertical"
    size_hint_y: None
    height: self.minimum_height
    spacing: dp(6)

<RecordRow>:
    size_hint_y: None
    height: max(dp(44), value_label.texture_size[1] + dp(20))
    padding: [dp(12), dp(10)]
    spacing: dp(10)
    canvas.before:
        Color:
            rgba: C_FIELD
        RoundedRectangle:
            pos: self.pos
            size: self.size
            radius: [dp(8)]
    Label:
        text: root.key
        color: C_MUTED
        font_size: "13sp"
        size_hint_x: 0.4
        text_size: self.size
        halign: "left"
        valign: "middle"
    Label:
        id: value_label
        text: root.value
        color: C_TEXT
        bold: True
        font_size: "14sp"
        text_size: self.width, None
        halign: "right"
        valign: "middle"


<MainScreen>:
    orientation: "vertical"
    canvas.before:
        Color:
            rgba: C_BG
        Rectangle:
            pos: self.pos
            size: self.size

    # ---------- HEADER ----------
    BoxLayout:
        size_hint_y: None
        height: dp(76)
        padding: [dp(20), dp(12)]
        canvas.before:
            Color:
                rgba: C_PRIMARY
            Rectangle:
                pos: self.pos
                size: self.size

        BoxLayout:
            orientation: "vertical"
            Label:
                text: "USC-V1"
                bold: True
                font_size: "22sp"
                color: 1, 1, 1, 1
                text_size: self.size
                halign: "left"
                valign: "bottom"
            Label:
                text: "Patient Device Manager"
                font_size: "12sp"
                color: 1, 1, 1, 0.8
                text_size: self.size
                halign: "left"
                valign: "top"

        BoxLayout:
            size_hint: None, None
            size: dp(122), dp(32)
            pos_hint: {"center_y": 0.5}
            padding: [dp(12), 0]
            spacing: dp(8)
            canvas.before:
                Color:
                    rgba: 1, 1, 1, 0.18
                RoundedRectangle:
                    pos: self.pos
                    size: self.size
                    radius: [dp(16)]
            Widget:
                size_hint: None, None
                size: dp(10), dp(10)
                pos_hint: {"center_y": 0.5}
                canvas:
                    Color:
                        rgba: STATE_DOT[root.connection]
                    Ellipse:
                        pos: self.pos
                        size: self.size
            Label:
                text: STATE_TEXT[root.connection]
                bold: True
                font_size: "13sp"
                color: 1, 1, 1, 1

    # ---------- CONTENT ----------
    ScrollView:
        do_scroll_x: False
        bar_width: dp(4)

        BoxLayout:
            orientation: "vertical"
            size_hint_y: None
            height: self.minimum_height
            padding: dp(16)
            spacing: dp(16)

            # Device card
            Card:
                SectionTitle:
                    text: "Device"

                Label:
                    text: root.status
                    color: STATUS_FG[root.status_kind]
                    font_size: "14sp"
                    size_hint_y: None
                    text_size: self.width - dp(24), None
                    height: self.texture_size[1] + dp(24)
                    halign: "left"
                    valign: "middle"
                    canvas.before:
                        Color:
                            rgba: STATUS_BG[root.status_kind]
                        RoundedRectangle:
                            pos: self.pos
                            size: self.size
                            radius: [dp(10)]

                AppButton:
                    text: {"scanning": "Scanning...", "connecting": "Connecting...", "connected": "Disconnect"}.get(root.connection, "Scan for Devices")
                    bg: C_DANGER if root.connection == "connected" else C_PRIMARY
                    disabled: root.connection in ("scanning", "connecting")
                    on_release: root.toggle_connection()

                OutlineButton:
                    text: "Sync Device Time"
                    disabled: root.connection != "connected"
                    on_release: root.sync_time()

            # Patient card
            Card:
                SectionTitle:
                    text: "Patient Details"

                FieldGroup:
                    FieldLabel:
                        text: "Patient name"
                    Field:
                        id: baby
                        hint_text: "e.g. Baby of Priya"

                FieldGroup:
                    FieldLabel:
                        text: "City"
                    Field:
                        id: city
                        hint_text: "e.g. Mumbai"

                FieldGroup:
                    FieldLabel:
                        text: "Location (latitude, longitude)"
                    BoxLayout:
                        size_hint_y: None
                        height: dp(48)
                        spacing: dp(8)
                        Field:
                            id: location
                            hint_text: "19.0760,72.8777"
                        OutlineButton:
                            text: "GPS"
                            size_hint_x: None
                            width: dp(64)
                            height: dp(48)
                            on_release: root.get_location()

                AppButton:
                    text: "Send Patient Data"
                    disabled: root.connection != "connected"
                    on_release: root.send_patient_data()

            # Hospital card: printed on the PDF only, not sent to the device
            Card:
                SectionTitle:
                    text: "Hospital Details (for PDF)"

                FieldGroup:
                    FieldLabel:
                        text: "Hospital name"
                    Field:
                        id: hospital
                        hint_text: "e.g. City Care Hospital"

                FieldGroup:
                    FieldLabel:
                        text: "Doctor name"
                    Field:
                        id: doctor
                        hint_text: "e.g. Dr. Sharma"

            # Record card
            Card:
                BoxLayout:
                    size_hint_y: None
                    height: dp(38)
                    SectionTitle:
                        text: "Patient Record"
                        height: dp(38)
                    OutlineButton:
                        text: "Request"
                        font_size: "14sp"
                        size_hint_x: None
                        width: dp(104)
                        height: dp(38)
                        disabled: root.connection != "connected"
                        on_release: root.request_record()

                Label:
                    text: "No record yet. Connect the device and tap Request."
                    color: C_MUTED
                    font_size: "13sp"
                    size_hint_y: None
                    height: 0 if root.has_record else dp(40)
                    opacity: 0 if root.has_record else 1
                    text_size: self.width, None
                    halign: "center"

                BoxLayout:
                    id: records_box
                    orientation: "vertical"
                    size_hint_y: None
                    height: self.minimum_height
                    spacing: dp(8)

                AppButton:
                    text: "Save as PDF"
                    height: dp(50) if root.has_record else 0
                    opacity: 1 if root.has_record else 0
                    disabled: not root.has_record
                    on_release: root.save_pdf()

            # Raw notifications, shown once the device sends anything
            Card:
                opacity: 1 if root.raw_log else 0
                disabled: not root.raw_log
                SectionTitle:
                    text: "Raw data from device"
                    font_size: "14sp"
                Label:
                    text: root.raw_log
                    font_name: "RobotoMono-Regular"
                    font_size: "12sp"
                    color: C_TEXT
                    size_hint_y: None
                    text_size: self.width, None
                    height: self.texture_size[1]
                    halign: "left"


<DeviceRow>:
    size_hint_y: None
    height: dp(64)
    padding: [dp(14), dp(8)]
    spacing: dp(10)
    canvas.before:
        Color:
            rgba: C_BORDER if self.state == "down" else ((0.886, 0.957, 0.957, 1) if self.recommended else C_FIELD)
        RoundedRectangle:
            pos: self.pos
            size: self.size
            radius: [dp(10)]
    BoxLayout:
        orientation: "vertical"
        Label:
            text: root.name or "Unknown device"
            bold: bool(root.name)
            color: C_TEXT if root.name else C_MUTED
            font_size: "15sp"
            text_size: self.size
            halign: "left"
            valign: "middle"
            shorten: True
            shorten_from: "right"
        Label:
            text: ("Recommended  |  " if root.recommended else "") + root.address
            color: C_PRIMARY if root.recommended else C_MUTED
            font_size: "12sp"
            text_size: self.size
            halign: "left"
            valign: "middle"
            shorten: True
    Label:
        text: "%d dBm" % root.rssi
        size_hint_x: None
        width: dp(72)
        font_size: "13sp"
        bold: True
        # Signal strength: green strong, amber medium, grey weak
        color: (0.082, 0.502, 0.239, 1) if root.rssi > -70 else ((0.706, 0.325, 0.035, 1) if root.rssi > -85 else C_MUTED)
        text_size: self.size
        halign: "right"
        valign: "middle"


<ScanDialog>:
    size_hint: 0.94, 0.82
    auto_dismiss: False
    background: ""
    background_color: 0, 0, 0, 0
    overlay_color: 0, 0, 0, 0.45

    BoxLayout:
        orientation: "vertical"
        padding: dp(18)
        spacing: dp(12)
        canvas.before:
            Color:
                rgba: 1, 1, 1, 1
            RoundedRectangle:
                pos: self.pos
                size: self.size
                radius: [dp(18)]

        SectionTitle:
            text: "Select Device"
            font_size: "19sp"

        Label:
            text: root.message
            color: C_MUTED
            font_size: "13sp"
            size_hint_y: None
            text_size: self.width, None
            height: max(dp(20), self.texture_size[1])
            halign: "left"

        ScrollView:
            do_scroll_x: False
            bar_width: dp(4)
            BoxLayout:
                id: device_list
                orientation: "vertical"
                size_hint_y: None
                height: self.minimum_height
                spacing: dp(8)

        OutlineButton:
            text: ("Hide" if root.show_unnamed else "Show") + " unnamed devices"
            font_size: "13sp"
            height: dp(38)
            on_release: root.show_unnamed = not root.show_unnamed

        BoxLayout:
            size_hint_y: None
            height: dp(50)
            spacing: dp(10)
            OutlineButton:
                text: "Cancel"
                on_release: root.cancel()
            AppButton:
                text: "Scanning..." if root.scanning else "Scan Again"
                disabled: root.scanning
                on_release: root.screen.start_scan()
"""


class AppButton(ButtonBehavior, Label):
    bg = ColorProperty([0.055, 0.486, 0.525, 1])
    fg = ColorProperty([1, 1, 1, 1])


class RecordRow(BoxLayout):
    key = StringProperty("")
    value = StringProperty("")


if platform == "android":
    from jnius import PythonJavaClass, cast, java_method

    class FusedLocationListener(PythonJavaClass):
        """Receives the result of a Google Play services location request."""

        __javainterfaces__ = [
            "com/google/android/gms/tasks/OnSuccessListener",
            "com/google/android/gms/tasks/OnFailureListener",
        ]
        # Play services classes live in the app, not the Android system
        __javacontext__ = "app"

        def __init__(self, on_location, on_error):
            super().__init__()
            self.on_location = on_location
            self.on_error = on_error

        @java_method("(Ljava/lang/Object;)V")
        def onSuccess(self, result):
            if result is None:
                self.on_location(None)
                return

            location = cast("android.location.Location", result)
            accuracy = location.getAccuracy() if location.hasAccuracy() else None
            self.on_location(
                (location.getLatitude(), location.getLongitude(), accuracy)
            )

        @java_method("(Ljava/lang/Exception;)V")
        def onFailure(self, error):
            self.on_error(error.toString())


class DeviceRow(ButtonBehavior, BoxLayout):
    name = StringProperty("")
    address = StringProperty("")
    rssi = NumericProperty(-100)
    recommended = BooleanProperty(False)


class ScanDialog(ModalView):
    """Lists BLE devices as they are discovered; tapping one connects to it."""

    message = StringProperty("")
    scanning = BooleanProperty(False)
    show_unnamed = BooleanProperty(False)

    def __init__(self, screen, **kwargs):
        super().__init__(**kwargs)
        self.screen = screen
        self.devices = {}   # address -> BLEDevice
        self.rows = {}      # address -> DeviceRow
        self.error = ""

    def clear(self):
        self.error = ""
        self.devices.clear()
        self.rows.clear()
        self.ids.device_list.clear_widgets()
        self.update_message()

    def add_device(self, device, name, rssi):
        address = device.address
        self.devices[address] = device

        row = self.rows.get(address)
        if row is None:
            row = DeviceRow(address=address)
            row.bind(on_release=lambda r: self.select(r.address))
            self.rows[address] = row

        # Scan responses can add a name later, so keep the first one we saw
        row.name = name or row.name
        row.rssi = rssi
        row.recommended = row.name == DEVICE_NAME

        self.place_row(row)
        self.update_message()

    def place_row(self, row):
        device_list = self.ids.device_list
        visible = bool(row.name) or self.show_unnamed

        if not visible:
            if row.parent:
                device_list.remove_widget(row)
            return

        if row.parent is None:
            # Recommended device goes to the top; others are appended below
            index = len(device_list.children) if row.recommended else 0
            device_list.add_widget(row, index=index)

    def on_show_unnamed(self, *args):
        device_list = self.ids.device_list
        device_list.clear_widgets()

        for row in self.sorted_rows():
            if row.name or self.show_unnamed:
                device_list.add_widget(row, index=0)

        self.update_message()

    def sorted_rows(self):
        return sorted(
            self.rows.values(),
            key=lambda r: (not r.recommended, not r.name, -r.rssi)
        )

    def finish_scan(self):
        self.scanning = False
        # Re-sort by signal strength now that rows are no longer arriving
        self.on_show_unnamed()

    def update_message(self):
        shown = len(self.ids.device_list.children)
        hidden = len(self.rows) - shown
        hidden_text = f" ({hidden} unnamed hidden)" if hidden else ""

        if self.error:
            self.message = self.error
        elif self.scanning:
            self.message = f"Searching... {shown} found{hidden_text}"
        elif self.rows:
            self.message = f"{shown} device(s) found{hidden_text}. Tap one to connect."
        else:
            self.message = "No devices found. Make sure the device is on and nearby, then scan again."

    def select(self, address):
        device = self.devices[address]
        name = self.rows[address].name or address
        self.dismiss()
        self.screen.connect_to(device, name)

    def cancel(self):
        self.screen.stop_scan()
        self.dismiss()
        if self.screen.connection == "scanning":
            self.screen.connection = "offline"


class MainScreen(BoxLayout):

    status = StringProperty("Tap Scan for Devices to find your device.")
    status_kind = OptionProperty("info", options=["info", "busy", "ok", "error"])
    connection = OptionProperty(
        "offline", options=["offline", "scanning", "connecting", "connected"]
    )
    has_record = BooleanProperty(False)
    raw_log = StringProperty("")

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self.client = None
        self.received_data = {}
        self.tasks = set()

        self.scan_dialog = None
        self.scan_running = False
        self.stop_scan_event = None

        self.gps_running = False
        self.gps_mode = None
        self.gps_listeners = []
        self.gps_best_accuracy = None
        self.gps_timeout_event = Clock.create_trigger(self.on_gps_timeout, GPS_TIMEOUT)

        self.raw_lines = []
        self.rx_buffer = ""
        self.line_mode = False
        self.record_done = True
        self.finish_event = Clock.create_trigger(self.finish_record, 2)
        self.no_reply_event = Clock.create_trigger(self.on_no_reply, 6)

        Clock.schedule_once(lambda dt: self.load_hospital())

        if platform == "android":
            # Android: Kivy runs on the asyncio loop (see __main__). BLE must
            # stay on this thread, since other Python threads can't load the
            # app's Java classes (bleak's PythonScanCallback).
            self.loop = None
        else:
            self.loop = asyncio.new_event_loop()

            threading.Thread(
                target=self.run_loop,
                daemon=True
            ).start()

    def run_loop(self):
        asyncio.set_event_loop(self.loop)
        self.loop.run_forever()

    def run_async(self, coroutine):
        if self.loop is None:
            task = asyncio.get_running_loop().create_task(coroutine)
            # Keep a reference so the task isn't garbage-collected mid-run
            self.tasks.add(task)
            task.add_done_callback(self.tasks.discard)
        else:
            asyncio.run_coroutine_threadsafe(
                coroutine, self.loop
            )

    def update_status(self, message, kind="info", connection=None):
        # Safe to call from the BLE thread: UI changes happen on the Kivy thread
        def apply(dt):
            self.status = message
            self.status_kind = kind
            if connection is not None:
                self.connection = connection

        Clock.schedule_once(apply)

    # BLE SCAN AND CONNECT

    def toggle_connection(self):
        if self.connection == "connected":
            self.disconnect_device()
        else:
            self.scan_device()

    def scan_device(self):
        if platform == "android":
            from jnius import autoclass

            # Android 12+ needs BLUETOOTH_SCAN/CONNECT; older versions need location
            permissions = ["android.permission.ACCESS_FINE_LOCATION"]
            if autoclass("android.os.Build$VERSION").SDK_INT >= 31:
                permissions += [
                    "android.permission.BLUETOOTH_SCAN",
                    "android.permission.BLUETOOTH_CONNECT",
                ]

            self.request_android_permissions(
                permissions, self.open_scan_dialog,
                "Bluetooth and location permissions are needed to find devices."
            )
        else:
            self.open_scan_dialog()

    def request_android_permissions(self, permissions, on_granted, denied_message):
        from android.permissions import request_permissions

        def callback(names, results):
            if all(results):
                Clock.schedule_once(lambda dt: on_granted())
            else:
                self.update_status(denied_message, "error")

        request_permissions(permissions, callback)

    def open_scan_dialog(self):
        self.scan_dialog = ScanDialog(self)
        self.scan_dialog.open()
        self.start_scan()

    def start_scan(self):
        if self.scan_running:
            return

        self.scan_running = True
        self.scan_dialog.clear()
        self.scan_dialog.scanning = True
        self.scan_dialog.update_message()
        self.connection = "scanning"
        self.run_async(self.scan_ble())

    async def scan_ble(self):
        dialog = self.scan_dialog
        self.stop_scan_event = asyncio.Event()

        def on_detect(device, advertisement):
            name = advertisement.local_name or device.name or ""
            rssi = advertisement.rssi
            Clock.schedule_once(
                lambda dt: dialog.add_device(device, name, rssi)
            )

        try:
            async with BleakScanner(detection_callback=on_detect):
                try:
                    await asyncio.wait_for(
                        self.stop_scan_event.wait(), SCAN_SECONDS
                    )
                except asyncio.TimeoutError:
                    pass

        except Exception as error:
            message = "Scan error: " + str(error)
            dialog.error = message
            self.update_status(message, "error")

        finally:
            self.scan_running = False

            def done(dt):
                if self.connection == "scanning":
                    self.connection = "offline"
                if dialog.scanning:
                    dialog.finish_scan()

            Clock.schedule_once(done)

    def stop_scan(self):
        event = self.stop_scan_event
        if event is not None and self.scan_running:
            loop = self.loop or asyncio.get_running_loop()
            loop.call_soon_threadsafe(event.set)

    def connect_to(self, device, name):
        self.stop_scan()
        self.update_status(f"Connecting to {name}...", "busy", "connecting")
        self.run_async(self.connect_ble(device, name))

    async def connect_ble(self, device, name):

        # Android can't connect reliably while a scan is still running
        while self.scan_running:
            await asyncio.sleep(0.05)

        try:
            self.client = BleakClient(
                device,
                disconnected_callback=self.on_ble_disconnected
            )
            await self.client.connect(timeout=20)

            try:
                await self.client.start_notify(
                    CHAR4_UUID,
                    self.notification_handler
                )
            except Exception:
                await self.client.disconnect()
                self.update_status(
                    f"{name} doesn't have the USC-V1 data channel (FFF4). "
                    "Choose the correct device.",
                    "error", "offline"
                )
                return

            self.update_status(f"Connected to {name}.", "ok", "connected")

        except Exception as error:
            self.update_status(
                f"Could not connect to {name}: {error}", "error", "offline"
            )

    def on_ble_disconnected(self, client):
        self.update_status("Device disconnected.", "info", "offline")

    # RECEIVE CHAR4 NOTIFICATIONS

    def notification_handler(self, sender, data):

        try:
            text = data.decode("utf-8", errors="replace")

            Clock.schedule_once(
                lambda dt: self.process_chunk(text)
            )

        except Exception as error:
            print("Notification error:", error)

    def process_chunk(self, text):
        # Show every notification exactly as received, for troubleshooting
        self.raw_lines.append(repr(text))
        self.raw_lines = self.raw_lines[-30:]
        self.raw_log = "\n".join(self.raw_lines)

        self.no_reply_event.cancel()

        # A notification may hold one message, several newline-separated
        # messages, or part of a message that continues in the next one.
        # Once a newline is seen, the device is treated as sending lines.
        text = text.replace("\r", "\n")

        if "\n" in text:
            self.line_mode = True

        if self.line_mode:
            self.rx_buffer += text
            *lines, self.rx_buffer = self.rx_buffer.split("\n")
        elif text.strip().upper() == "END":
            lines = [self.rx_buffer, text]
            self.rx_buffer = ""
        else:
            # Without newlines, the held chunk was a complete message unless
            # this chunk turns out to continue it (handled by line_mode above)
            lines = [self.rx_buffer]
            self.rx_buffer = text

        for line in lines:
            self.process_message(line)

        if not self.record_done:
            self.status = f"Receiving record... ({len(self.received_data)} fields)"
            self.status_kind = "busy"
            # If the device never sends END, show what arrived after a pause
            self.finish_event()

    def process_message(self, message):

        message = message.strip()

        if not message:
            return

        if message.upper() == "END":
            self.finish_record(ended=True)
            return

        if ":" in message:
            key, value = message.split(":", 1)
            self.received_data[key.strip()] = value

    def finish_record(self, dt=None, ended=False):

        if self.record_done:
            return

        if self.rx_buffer.strip():
            leftover, self.rx_buffer = self.rx_buffer, ""
            self.process_message(leftover)

        self.finish_event.cancel()
        self.show_record()

        if not self.received_data:
            self.status = "Device replied, but no KEY:value fields were found. See raw data below."
            self.status_kind = "error"
        elif ended:
            self.status = "Record received successfully."
            self.status_kind = "ok"
        else:
            self.status = "Record received (device did not send END)."
            self.status_kind = "ok"

        self.record_done = True

    def on_no_reply(self, dt):
        self.status = "No reply from the device. Check that it supports the Q: request."
        self.status_kind = "error"

    def record_rows(self):
        # (label, value) pairs of the received record, as shown on screen
        rows = []

        for key, value in self.received_data.items():
            value = value.strip()

            if key == "T":
                # Device time arrives as YYMMDDhhmmss
                try:
                    value = datetime.strptime(value, "%y%m%d%H%M%S").strftime(
                        "%d %b %Y, %H:%M:%S"
                    )
                except ValueError:
                    pass

            rows.append((KEY_LABELS.get(key, key), value))

        return rows

    def show_record(self):
        box = self.ids.records_box
        box.clear_widgets()

        for label, value in self.record_rows():
            box.add_widget(RecordRow(key=label, value=value))

        self.has_record = bool(self.received_data)

    # SAVE RECORD AS PDF

    def save_pdf(self):

        if not self.received_data:
            self.update_status("No record to save. Tap Request first.", "error")
            return

        if platform == "android":
            from jnius import autoclass

            # Android 10+ saves to Downloads without any permission
            if autoclass("android.os.Build$VERSION").SDK_INT < 29:
                self.request_android_permissions(
                    ["android.permission.WRITE_EXTERNAL_STORAGE"],
                    self.write_pdf,
                    "Storage permission is needed to save the PDF."
                )
                return

        self.write_pdf()

    def settings_store(self):
        from kivy.storage.jsonstore import JsonStore
        return JsonStore(os.path.join(App.get_running_app().user_data_dir, "settings.json"))

    def load_hospital(self):
        # Hospital and doctor rarely change, so remember them between runs
        try:
            store = self.settings_store()
            if store.exists("hospital"):
                saved = store.get("hospital")
                self.ids.hospital.text = saved.get("hospital", "")
                self.ids.doctor.text = saved.get("doctor", "")
        except Exception as error:
            print("Could not load hospital details:", error)

    def write_pdf(self):

        hospital = self.ids.hospital.text.strip()
        doctor = self.ids.doctor.text.strip()

        try:
            self.settings_store().put("hospital", hospital=hospital, doctor=doctor)
        except Exception as error:
            print("Could not save hospital details:", error)

        # The hospital is where the baby was born: use the record's city and location
        born_place = ", ".join(
            value for value in (
                self.received_data.get("C", "").strip(),
                self.received_data.get("L", "").strip(),
            ) if value
        )

        now = datetime.now()
        data = build_pdf(
            self.record_rows(),
            title=hospital or "USC-V1 Patient Report",
            subtitle=("Location: " + born_place) if born_place else "",
            info=("Doctor: " + doctor) if doctor else "",
            generated="Generated on " + now.strftime("%d %b %Y, %H:%M:%S"),
            heading="Patient Record",
        )

        name = self.received_data.get("N", "").strip() or "patient"
        name = "".join(c if c.isalnum() else "_" for c in name).strip("_")
        filename = "%s_%s.pdf" % (name or "patient", now.strftime("%Y%m%d_%H%M%S"))

        try:
            if platform == "android":
                where = self.save_pdf_android(filename, data)
            else:
                folder = os.path.join(os.path.expanduser("~"), "Downloads")
                if not os.path.isdir(folder):
                    folder = os.getcwd()
                where = os.path.join(folder, filename)
                with open(where, "wb") as file:
                    file.write(data)
        except Exception as error:
            self.update_status("Could not save PDF: " + str(error), "error")
            return

        self.update_status("PDF saved: " + where, "ok")

    def save_pdf_android(self, filename, data):
        from jnius import autoclass

        Build = autoclass("android.os.Build$VERSION")
        activity = autoclass("org.kivy.android.PythonActivity").mActivity

        if Build.SDK_INT < 29:
            Environment = autoclass("android.os.Environment")
            folder = os.path.join(
                Environment.getExternalStoragePublicDirectory(
                    Environment.DIRECTORY_DOWNLOADS
                ).getAbsolutePath(),
                "USC-V1"
            )
            os.makedirs(folder, exist_ok=True)
            path = os.path.join(folder, filename)
            with open(path, "wb") as file:
                file.write(data)
            return path

        # Android 10+: add the file to the shared Downloads folder via MediaStore
        ContentValues = autoclass("android.content.ContentValues")
        Downloads = autoclass("android.provider.MediaStore$Downloads")

        values = ContentValues()
        values.put("_display_name", filename)
        values.put("mime_type", "application/pdf")
        values.put("relative_path", "Download/USC-V1")

        resolver = activity.getContentResolver()
        uri = resolver.insert(Downloads.EXTERNAL_CONTENT_URI, values)
        if uri is None:
            raise OSError("Android refused to create the file")

        stream = resolver.openOutputStream(uri)
        try:
            stream.write(data)
        finally:
            stream.close()

        # Open it in the phone's PDF viewer, if there is one
        try:
            Intent = autoclass("android.content.Intent")
            intent = Intent(Intent.ACTION_VIEW)
            intent.setDataAndType(uri, "application/pdf")
            intent.addFlags(
                Intent.FLAG_GRANT_READ_URI_PERMISSION | Intent.FLAG_ACTIVITY_NEW_TASK
            )
            activity.startActivity(intent)
        except Exception as error:
            print("No app to open the PDF:", error)

        return "Download/USC-V1/" + filename

    # SEND CHAR3 DATA

    async def write_ble(self, message):

        if self.client is None or not self.client.is_connected:
            self.update_status("Please connect the device first.", "error")
            return False

        try:
            await self.client.write_gatt_char(
                CHAR3_UUID,
                message.encode("utf-8"),
                response=True
            )
            return True

        except Exception as error:
            if "Invalid Attribute Value Length" in str(error):
                self.update_status(
                    f"Device rejected '{message}': it is "
                    f"{len(message.encode('utf-8'))} bytes, more than the "
                    "device firmware accepts in one write.",
                    "error"
                )
            else:
                self.update_status("Write error: " + str(error), "error")
            return False

    def send_patient_data(self):

        baby = self.ids.baby.text.strip()
        city = self.ids.city.text.strip()
        location = self.ids.location.text.strip()

        if not baby or not city or not location:
            self.update_status("Please fill in all patient details.", "error")
            return

        self.update_status("Sending patient data...", "busy")
        self.run_async(self.send_data_sequence(
            baby, city, location
        ))

    async def send_data_sequence(self, baby, city, location):

        messages = [
            "N:" + baby,
            "C:" + city,
            "L:" + self.fit_location(location)
        ]

        for message in messages:
            if not await self.write_ble(message):
                return
            await asyncio.sleep(0.3)

        self.update_status("Patient data sent.", "ok")

    def fit_location(self, location):
        # Use as many decimals as fit in one device write
        # (5 decimals is about 1 m, 4 decimals about 11 m)
        try:
            lat, lon = (float(part) for part in location.split(","))
        except ValueError:
            return location

        for decimals in (6, 5, 4, 3):
            text = f"{lat:.{decimals}f},{lon:.{decimals}f}"
            if len(("L:" + text).encode("utf-8")) <= MAX_WRITE_BYTES:
                return text

        return text

    # SYNC RTC

    def sync_time(self):
        self.run_async(self.sync_time_ble())

    async def sync_time_ble(self):

        now = datetime.now()

        timestamp = now.strftime("%y%m%d%H%M%S")

        if await self.write_ble("T:" + timestamp):
            self.update_status(
                "Device time synced to " + now.strftime("%d %b %Y, %H:%M:%S") + ".",
                "ok"
            )

    # GPS LOCATION

    def get_location(self):

        if platform != "android":
            self.update_status(
                "GPS works in the phone app. On this computer, type the coordinates.",
                "info"
            )
            return

        if self.gps_running:
            return

        self.request_android_permissions(
            [
                "android.permission.ACCESS_FINE_LOCATION",
                "android.permission.ACCESS_COARSE_LOCATION",
            ],
            self.start_gps,
            "Location permission is needed to read GPS."
        )

    def start_gps(self):

        try:
            if not self.location_services_on():
                self.update_status(
                    "Location is turned off. Turn on Location in phone settings and try again.",
                    "error"
                )
                return
        except Exception as error:
            print("Could not check location settings:", error)

        self.gps_running = True
        self.gps_best_accuracy = None
        self.gps_timeout_event()
        self.update_status("Getting location...", "busy")

        try:
            self.start_fused_location()
        except Exception as error:
            # No Google Play services (e.g. some Huawei phones): use plain GPS
            print("Google location unavailable, using GPS:", error)
            self.start_plyer_gps()

    def start_fused_location(self):
        # Google Play services' fused location: the same source Google Maps
        # uses (GPS + Wi-Fi + mobile network), so it also works indoors
        from jnius import autoclass

        LocationServices = autoclass(
            "com.google.android.gms.location.LocationServices"
        )
        activity = autoclass("org.kivy.android.PythonActivity").mActivity
        client = LocationServices.getFusedLocationProviderClient(activity)

        self.gps_mode = "fused"

        # Last known location gives an instant answer; the current location
        # request then replaces it with a fresh, accurate fix
        last = FusedLocationListener(
            lambda values: self.on_fused_location(values, final=False),
            self.on_fused_error
        )
        current = FusedLocationListener(
            lambda values: self.on_fused_location(values, final=True),
            self.on_fused_error
        )
        # Keep references, or Python may garbage-collect the Java listeners
        self.gps_listeners = [last, current]

        task = client.getLastLocation()
        task.addOnSuccessListener(last)
        task.addOnFailureListener(last)

        task = client.getCurrentLocation(PRIORITY_HIGH_ACCURACY, None)
        task.addOnSuccessListener(current)
        task.addOnFailureListener(current)

    def on_fused_location(self, values, final):
        # Called on the Android UI thread: hand over to the Kivy thread
        Clock.schedule_once(lambda dt: self.handle_fused_location(values, final))

    def handle_fused_location(self, values, final):

        if not self.gps_running or self.gps_mode != "fused":
            return

        if values is not None:
            # A last-known location may be old, so wait for the fresh one
            self.set_gps_location(*values, allow_finish=final)

        if final and self.gps_running:
            if self.gps_best_accuracy is None:
                # Google could not get a fix; try the phone's GPS directly
                self.start_plyer_gps()
            else:
                self.finish_gps()

    def on_fused_error(self, message):
        def fallback(dt):
            if self.gps_running and self.gps_mode == "fused":
                print("Google location failed, using GPS:", message)
                self.start_plyer_gps()

        Clock.schedule_once(fallback)

    def start_plyer_gps(self):
        from plyer import gps

        self.gps_mode = "plyer"

        try:
            gps.configure(
                on_location=self.on_gps_location,
                on_status=self.on_gps_status
            )
            gps.start(minTime=1000, minDistance=0)
        except Exception as error:
            self.gps_running = False
            self.gps_timeout_event.cancel()
            self.update_status("GPS error: " + str(error), "error")
            return

        if self.gps_best_accuracy is None:
            self.update_status("Getting GPS location... (works best outdoors)", "busy")

    def location_services_on(self):
        from jnius import autoclass, cast

        Context = autoclass("android.content.Context")
        activity = autoclass("org.kivy.android.PythonActivity").mActivity
        manager = cast(
            "android.location.LocationManager",
            activity.getSystemService(Context.LOCATION_SERVICE)
        )
        return (
            manager.isProviderEnabled("gps")
            or manager.isProviderEnabled("network")
        )

    def stop_gps(self):
        if not self.gps_running:
            return

        self.gps_running = False
        self.gps_timeout_event.cancel()
        self.gps_listeners = []

        # Fused location requests are one-shot; only plain GPS needs stopping
        if self.gps_mode == "plyer":
            from plyer import gps

            try:
                gps.stop()
            except Exception as error:
                print("GPS stop error:", error)

    def finish_gps(self):
        self.stop_gps()
        self.update_status(
            f"Location set (accurate to {self.gps_best_accuracy:.0f} m).", "ok"
        )

    def on_gps_location(self, **kwargs):
        # Called on the Android UI thread: hand over to the Kivy thread
        Clock.schedule_once(lambda dt: self.set_gps_location(**kwargs))

    def set_gps_location(self, lat, lon, accuracy=None, allow_finish=True, **kwargs):

        if not self.gps_running:
            return

        accuracy = accuracy if accuracy else 9999

        # Keep refining until the fix is accurate enough
        if self.gps_best_accuracy is not None and accuracy >= self.gps_best_accuracy:
            return

        self.gps_best_accuracy = accuracy
        self.ids.location.text = f"{lat:.6f},{lon:.6f}"

        if accuracy <= GPS_GOOD_ACCURACY and allow_finish:
            self.finish_gps()
        else:
            self.update_status(
                f"Location found (±{accuracy:.0f} m). Improving accuracy...", "busy"
            )

    def on_gps_status(self, stype, status):
        print("GPS status:", stype, status)

    def on_gps_timeout(self, dt):

        if not self.gps_running:
            return

        if self.gps_best_accuracy is None:
            self.stop_gps()
            self.update_status(
                "Could not get a location. Check that Location is on, go near "
                "a window or outdoors, and try again.",
                "error"
            )
        else:
            self.finish_gps()

    # REQUEST RECORD

    def request_record(self):

        self.received_data.clear()
        self.ids.records_box.clear_widgets()
        self.has_record = False

        self.raw_lines = []
        self.raw_log = ""
        self.rx_buffer = ""
        self.line_mode = False
        self.record_done = False
        self.finish_event.cancel()
        self.no_reply_event()

        self.update_status("Requesting device record...", "busy")
        self.run_async(
            self.write_ble("Q:")
        )

    # DISCONNECT

    def disconnect_device(self):
        self.run_async(self.disconnect_ble())

    async def disconnect_ble(self):

        if self.client and self.client.is_connected:
            await self.client.disconnect()

        self.update_status("Disconnected.", "info", "offline")


class USCV1App(App):

    title = "USC-V1"

    def build(self):
        if platform in ("android", "ios"):
            # Keep the focused text field visible above the on-screen keyboard
            Window.softinput_mode = "below_target"
        else:
            # Phone-sized window when previewing on a computer
            Window.size = (400, 800)

        Builder.load_string(KV)
        return MainScreen()


if __name__ == "__main__":
    if platform == "android":
        asyncio.run(USCV1App().async_run(async_lib="asyncio"))
    else:
        USCV1App().run()
