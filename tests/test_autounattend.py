"""Unit tests for install_files: autounattend.xml builder + floppy builder."""

from __future__ import annotations

import os
import shutil
import subprocess
import xml.dom.minidom

import pytest

from install_files import floppy
from install_files.autounattend import (
    ADMIN_PASSWORD,
    COMPUTER_NAME,
    MARKER_URL,
    PRODUCT_KEY,
    build_autounattend,
)

# Microsoft's official GVLK for Windows IoT Enterprise LTSC 2024/2021
# (learn.microsoft.com KMS client activation keys). Asserted explicitly so
# any deliberate change to the constant must be a conscious decision.
OFFICIAL_GVLK = "KBN8V-HFGQ4-MGXVD-347P6-PDQGT"

FILE_BIN = shutil.which("file") or "/usr/bin/file"
MDIR_BIN = os.path.join(os.path.dirname(floppy.MCOPY), "mdir")
MTYPE_BIN = os.path.join(os.path.dirname(floppy.MCOPY), "mtype")


def _text_of(doc: xml.dom.minidom.Document, tag: str) -> str:
    """Return the concatenated text of the first element with the given tag."""
    elements = doc.getElementsByTagName(tag)
    assert elements, f"expected element <{tag}>"
    return _text_of_element(elements[0])


def _text_of_element(parent: xml.dom.minidom.Element) -> str:
    """Return the concatenated text of the element's direct text nodes."""
    return "".join(
        node.data for node in parent.childNodes if node.nodeType == node.TEXT_NODE
    )


def _child_text(parent: xml.dom.minidom.Element, tag: str) -> str:
    """Return the text of the first direct child element with the given tag."""
    for child in parent.childNodes:
        if child.nodeType == child.ELEMENT_NODE and child.tagName == tag:
            return _text_of_element(child)
    raise AssertionError(f"expected child element <{tag}>")


def test_autounattend_is_well_formed():
    """The generated XML parses without exceptions."""
    xml_str = build_autounattend(1)

    doc = xml.dom.minidom.parseString(xml_str)

    assert doc.documentElement.tagName == "unattend"


def test_product_key_is_official_public_gvlk():
    """ProductKey carries the official KMS GVLK, not a hardcoded wrong key."""
    doc = xml.dom.minidom.parseString(build_autounattend(1))

    assert PRODUCT_KEY == OFFICIAL_GVLK
    product_key = doc.getElementsByTagName("ProductKey")[0]
    assert _child_text(product_key, "Key") == PRODUCT_KEY


def test_administrator_password_and_autologon_use_devbox_password():
    """Local admin password and auto-logon share Devbox123! in plain text."""
    doc = xml.dom.minidom.parseString(build_autounattend(1))

    assert ADMIN_PASSWORD == "Devbox123!"
    admin_password = doc.getElementsByTagName("AdministratorPassword")[0]
    assert _child_text(admin_password, "Value") == "Devbox123!"
    assert _child_text(admin_password, "PlainText") == "true"
    password = doc.getElementsByTagName("Password")[0]
    assert _child_text(password, "Value") == "Devbox123!"
    assert _text_of(doc, "Username") == "Administrator"


def test_computer_name_and_timezone():
    """specialize pass sets WIN-DEVBOX and UTC."""
    doc = xml.dom.minidom.parseString(build_autounattend(1))

    assert _text_of(doc, "ComputerName") == COMPUTER_NAME == "WIN-DEVBOX"
    assert _text_of(doc, "TimeZone") == "UTC"


def test_accept_eula_is_true():
    """windowsPE UserData accepts the EULA so setup never prompts."""
    doc = xml.dom.minidom.parseString(build_autounattend(1))

    assert _text_of(doc, "AcceptEula") == "true"


@pytest.mark.parametrize("index", [1, 2])
def test_image_index_is_parameterized(index):
    """The emitted /IMAGE/INDEX value equals the requested index (never fixed)."""
    xml_str = build_autounattend(index)
    doc = xml.dom.minidom.parseString(xml_str)

    # Raw-string check per spec: each build emits exactly its own index.
    assert f"<Value>{index}</Value>" in xml_str

    # DOM check: the MetaData Key=/IMAGE/INDEX element carries str(index).
    metadata = doc.getElementsByTagName("MetaData")
    assert len(metadata) == 1
    index_meta = metadata[0]
    assert _text_of(index_meta, "Key") == "/IMAGE/INDEX"
    assert _text_of(index_meta, "Value") == str(index)


def test_index_1_does_not_emit_index_2():
    """Index 1 build must not contain the reference repo's hardcoded 2."""
    xml_str = build_autounattend(1)

    assert "<Value>2</Value>" not in xml_str
    assert "<Value>1</Value>" in xml_str


def test_first_logon_commands_exactly_four_with_marker_last():
    """Exactly 4 commands in order; the /mark POST is last and unbroken."""
    doc = xml.dom.minidom.parseString(build_autounattend(1))

    commands = doc.getElementsByTagName("SynchronousCommand")
    assert len(commands) == 4

    command_lines = [_text_of(command, "CommandLine") for command in commands]
    assert command_lines[0].startswith('reg add "HKLM\\SYSTEM\\CurrentControlSet')
    assert command_lines[1].startswith("netsh advfirewall firewall add rule name=RDP")
    assert "standby-timeout-ac 0" in command_lines[2]
    assert "sleep-timeout-ac 0" in command_lines[2]

    marker = command_lines[3]
    assert marker == (
        'powershell -Command "Invoke-WebRequest -Uri '
        f"{MARKER_URL} -Method POST -Body 'installed'\""
    )
    assert MARKER_URL == "http://10.0.2.2:8765/mark"
    assert MARKER_URL in marker


def test_floppy_is_fat12_and_contains_autounattend_xml(tmp_path):
    """A built floppy is FAT12 and round-trips autounattend.xml verbatim."""
    xml_str = build_autounattend(1)
    image = tmp_path / "floppy.img"

    floppy.build_floppy(xml_str, str(image))

    file_type = subprocess.run(
        [FILE_BIN, "-s", str(image)], capture_output=True, text=True, check=True
    )
    assert "FAT (12 bit)" in file_type.stdout

    mdir = subprocess.run(
        [MDIR_BIN, "-i", str(image)], capture_output=True, text=True, check=True
    )
    # VFAT long names keep their original case: mdir shows "autounattend.xml".
    assert "autounattend.xml" in mdir.stdout.lower()

    mtype = subprocess.run(
        [MTYPE_BIN, "-i", str(image), "::AUTOUNATTEND.XML"],
        capture_output=True,
        text=True,
        check=True,
    )
    assert mtype.stdout == xml_str
