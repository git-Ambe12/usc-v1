import asyncio
import threading
from datetime import datetime

from kivy.app import App
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.lang import Builder
from kivy.properties import (
    BooleanProperty, ColorProperty, OptionProperty, StringProperty
)
from kivy.uix.behaviors import ButtonBehavior
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.utils import platform

from bleak import BleakScanner, BleakClient


# BLE CONFIGURATION
DEVICE_NAME = "Basic BLE project"

# Replace with your actual Service UUID if required
CHAR3_UUID = "0000fff3-0000-1000-8000-00805f9b34fb"
CHAR4_UUID = "0000fff4-0000-1000-8000-00805f9b34fb"

# Friendly names for record keys sent by the device
KEY_LABELS = {
    "N": "Baby Name",
    "C": "City",
    "L": "Location",
    "T": "Device Time",
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

#:set STATE_DOT {"offline": (0.612, 0.639, 0.686, 1), "scanning": (0.984, 0.749, 0.141, 1), "connected": (0.290, 0.871, 0.502, 1)}
#:set STATE_TEXT {"offline": "Offline", "scanning": "Scanning", "connected": "Connected"}
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
                    text: "Scanning..." if root.connection == "scanning" else ("Disconnect" if root.connection == "connected" else "Scan & Connect")
                    bg: C_DANGER if root.connection == "connected" else C_PRIMARY
                    disabled: root.connection == "scanning"
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
                        text: "Baby name"
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
"""


class AppButton(ButtonBehavior, Label):
    bg = ColorProperty([0.055, 0.486, 0.525, 1])
    fg = ColorProperty([1, 1, 1, 1])


class RecordRow(BoxLayout):
    key = StringProperty("")
    value = StringProperty("")


class MainScreen(BoxLayout):

    status = StringProperty("Tap Scan & Connect to find your device.")
    status_kind = OptionProperty("info", options=["info", "busy", "ok", "error"])
    connection = OptionProperty("offline", options=["offline", "scanning", "connected"])
    has_record = BooleanProperty(False)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self.client = None
        self.received_data = {}
        self.tasks = set()

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
            self.request_android_permissions(self.start_scan)
        else:
            self.start_scan()

    def start_scan(self):
        self.update_status("Scanning for nearby BLE devices...", "busy", "scanning")
        self.run_async(self.connect_ble())

    def request_android_permissions(self, on_granted):
        # Android 12+ needs BLUETOOTH_SCAN/CONNECT; older versions need location
        from android.permissions import request_permissions
        from jnius import autoclass

        sdk = autoclass("android.os.Build$VERSION").SDK_INT

        permissions = ["android.permission.ACCESS_FINE_LOCATION"]
        if sdk >= 31:
            permissions += [
                "android.permission.BLUETOOTH_SCAN",
                "android.permission.BLUETOOTH_CONNECT",
            ]

        def callback(names, results):
            if all(results):
                Clock.schedule_once(lambda dt: on_granted())
            else:
                self.update_status(
                    "Bluetooth and location permissions are needed to find the device.",
                    "error", "offline"
                )

        request_permissions(permissions, callback)

    async def connect_ble(self):

        try:
            devices = await BleakScanner.discover(
                timeout=8
            )

            target = None

            for device in devices:
                if device.name == DEVICE_NAME:
                    target = device
                    break

            if target is None:
                self.update_status(
                    f'"{DEVICE_NAME}" not found. Make sure it is powered on and nearby.',
                    "error", "offline"
                )
                return

            self.update_status(f"Connecting to {DEVICE_NAME}...", "busy")

            self.client = BleakClient(
                target,
                disconnected_callback=self.on_ble_disconnected
            )
            await self.client.connect()

            if self.client.is_connected:

                await self.client.start_notify(
                    CHAR4_UUID,
                    self.notification_handler
                )

                self.update_status(f"Connected to {DEVICE_NAME}.", "ok", "connected")

        except Exception as error:
            self.update_status("BLE error: " + str(error), "error", "offline")

    def on_ble_disconnected(self, client):
        self.update_status("Device disconnected.", "info", "offline")

    # RECEIVE CHAR4 NOTIFICATIONS

    def notification_handler(self, sender, data):

        try:
            message = data.decode("utf-8").strip()

            Clock.schedule_once(
                lambda dt: self.process_message(message)
            )

        except Exception as error:
            print("Notification error:", error)

    def process_message(self, message):

        if message == "END":
            self.show_record()
            self.status = "Record received successfully."
            self.status_kind = "ok"
            return

        if ":" in message:
            key, value = message.split(":", 1)
            self.received_data[key] = value

    def show_record(self):
        box = self.ids.records_box
        box.clear_widgets()

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

            box.add_widget(RecordRow(
                key=KEY_LABELS.get(key, key),
                value=value
            ))

        self.has_record = bool(self.received_data)

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
            "L:" + location
        ]

        for message in messages:
            if not await self.write_ble(message):
                return
            await asyncio.sleep(0.3)

        self.update_status("Patient data sent.", "ok")

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

    # GPS PLACEHOLDER

    def get_location(self):
        self.update_status(
            "GPS is not available yet. Please type the coordinates.",
            "info"
        )

    # REQUEST RECORD

    def request_record(self):

        self.received_data.clear()
        self.ids.records_box.clear_widgets()
        self.has_record = False

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
