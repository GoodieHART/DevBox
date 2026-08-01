"""Builder for the Windows Setup unattended-install answer file (autounattend.xml).

Adapted from modal-projects/windows-sandboxes/commands/install_windows.py
(MIT License): https://github.com/modal-projects/windows-sandboxes

Targets Windows 11 IoT Enterprise LTSC 2024 on a UEFI (OVMF) disk:
windowsPE disk partitioning (EFI + MSR + Primary), image index is a
parameter (resolved at install time via ``wiminfo`` — never hardcoded),
then specialize (computer name/time zone) and oobeSystem (local admin,
auto-logon, and the FirstLogonCommands that enable RDP and post the
install-done marker to the host RPC server).
"""

from __future__ import annotations

from xml.sax.saxutils import escape

# Public Microsoft KMS GVLK (generic volume license key) for Windows 11
# IoT Enterprise LTSC 2024 (shared with LTSC 2021), from the official
# learn.microsoft.com "KMS client activation keys" page. Installing with a
# GVLK leaves Windows UNACTIVATED — no activation is performed anywhere in
# this project.
PRODUCT_KEY = "KBN8V-HFGQ4-MGXVD-347P6-PDQGT"

ADMIN_PASSWORD = "Devbox123!"
COMPUTER_NAME = "WIN-DEVBOX"
# Guest->host install-done marker: over SLIRP user networking the guest's
# default gateway is 10.0.2.2, which the RPC server (port 8765) listens on.
MARKER_URL = "http://10.0.2.2:8765/mark"

# Exactly four FirstLogonCommands, in order. Command 3 runs both powercfg
# changes in one cmd.exe line ("&" chains commands; XML-escaped below).
_FIRST_LOGON_COMMANDS: tuple[tuple[str, str], ...] = (
    (
        'reg add "HKLM\\SYSTEM\\CurrentControlSet\\Control\\Terminal Server" '
        "/v fDenyTSConnections /t REG_DWORD /d 0 /f",
        "Enable Remote Desktop (Terminal Server)",
    ),
    (
        "netsh advfirewall firewall add rule name=RDP dir=in action=allow "
        "protocol=TCP localport=3389",
        "Allow RDP through the firewall",
    ),
    (
        "powercfg /change standby-timeout-ac 0 "
        "& powercfg /change sleep-timeout-ac 0",
        "Disable standby and sleep on AC",
    ),
    (
        'powershell -Command "Invoke-WebRequest -Uri '
        f"{MARKER_URL} -Method POST -Body 'installed'\"",
        "Notify host that installation finished",
    ),
)

# Escape quotes too (beyond the &, <, > defaults) so command lines with
# embedded quotes survive XML round-trips; Windows Setup decodes them back.
_XML_EXTRA_ENTITIES: dict[str, str] = {'"': "&quot;"}


def build_autounattend(index: int) -> str:
    """Return the complete autounattend.xml for the given WIM image index.

    Args:
        index: Image index inside the install ISO (e.g. ``1`` for the
            single-edition IoT Enterprise LTSC 2024 DVD; resolved at
            install time via ``wiminfo``).

    Returns:
        The full unattend XML document as a string.
    """
    first_logon = "\n".join(
        f"""        <SynchronousCommand wcm:action="add">
          <Order>{order}</Order>
          <CommandLine>{escape(command, _XML_EXTRA_ENTITIES)}</CommandLine>
          <Description>{escape(description, _XML_EXTRA_ENTITIES)}</Description>
        </SynchronousCommand>"""
        for order, (command, description) in enumerate(_FIRST_LOGON_COMMANDS, start=1)
    )

    key = escape(PRODUCT_KEY, _XML_EXTRA_ENTITIES)
    password = escape(ADMIN_PASSWORD, _XML_EXTRA_ENTITIES)
    image_index = escape(str(index), _XML_EXTRA_ENTITIES)

    return f"""\
<?xml version="1.0" encoding="utf-8"?>
<unattend xmlns="urn:schemas-microsoft-com:unattend"
         xmlns:wcm="http://schemas.microsoft.com/WMIConfig/2002/State">

  <settings pass="windowsPE">
    <component name="Microsoft-Windows-International-Core-WinPE"
               processorArchitecture="amd64" publicKeyToken="31bf3856ad364e35"
               language="neutral" versionScope="nonSxS">
      <SetupUILanguage><UILanguage>en-US</UILanguage></SetupUILanguage>
      <InputLocale>en-US</InputLocale>
      <SystemLocale>en-US</SystemLocale>
      <UILanguage>en-US</UILanguage>
      <UserLocale>en-US</UserLocale>
    </component>
    <component name="Microsoft-Windows-Setup"
               processorArchitecture="amd64" publicKeyToken="31bf3856ad364e35"
               language="neutral" versionScope="nonSxS">
      <DiskConfiguration>
        <Disk wcm:action="add">
          <DiskID>0</DiskID>
          <WillWipeDisk>true</WillWipeDisk>
          <CreatePartitions>
            <CreatePartition wcm:action="add">
              <Order>1</Order>
              <Type>EFI</Type>
              <Size>512</Size>
            </CreatePartition>
            <CreatePartition wcm:action="add">
              <Order>2</Order>
              <Type>MSR</Type>
              <Size>128</Size>
            </CreatePartition>
            <CreatePartition wcm:action="add">
              <Order>3</Order>
              <Type>Primary</Type>
              <Extend>true</Extend>
            </CreatePartition>
          </CreatePartitions>
          <ModifyPartitions>
            <ModifyPartition wcm:action="add">
              <Order>1</Order>
              <PartitionID>1</PartitionID>
              <Format>FAT32</Format>
              <Label>System</Label>
            </ModifyPartition>
            <ModifyPartition wcm:action="add">
              <Order>2</Order>
              <PartitionID>2</PartitionID>
            </ModifyPartition>
            <ModifyPartition wcm:action="add">
              <Order>3</Order>
              <PartitionID>3</PartitionID>
              <Format>NTFS</Format>
              <Label>Windows</Label>
            </ModifyPartition>
          </ModifyPartitions>
        </Disk>
      </DiskConfiguration>
      <ImageInstall>
        <OSImage>
          <InstallTo>
            <DiskID>0</DiskID>
            <PartitionID>3</PartitionID>
          </InstallTo>
          <InstallFrom>
            <MetaData wcm:action="add">
              <Key>/IMAGE/INDEX</Key>
              <Value>{image_index}</Value>
            </MetaData>
          </InstallFrom>
        </OSImage>
      </ImageInstall>
      <UserData>
        <AcceptEula>true</AcceptEula>
        <ProductKey>
          <Key>{key}</Key>
          <WillShowUI>Never</WillShowUI>
        </ProductKey>
      </UserData>
    </component>
  </settings>

  <settings pass="specialize">
    <component name="Microsoft-Windows-Shell-Setup"
               processorArchitecture="amd64" publicKeyToken="31bf3856ad364e35"
               language="neutral" versionScope="nonSxS">
      <ComputerName>{COMPUTER_NAME}</ComputerName>
      <TimeZone>UTC</TimeZone>
    </component>
  </settings>

  <settings pass="oobeSystem">
    <component name="Microsoft-Windows-Shell-Setup"
               processorArchitecture="amd64" publicKeyToken="31bf3856ad364e35"
               language="neutral" versionScope="nonSxS">
      <OOBE>
        <HideEULAPage>true</HideEULAPage>
        <HideLocalAccountScreen>true</HideLocalAccountScreen>
        <HideOEMRegistrationScreen>true</HideOEMRegistrationScreen>
        <HideOnlineAccountScreens>true</HideOnlineAccountScreens>
        <HideWirelessSetupInOOBE>true</HideWirelessSetupInOOBE>
        <ProtectYourPC>3</ProtectYourPC>
        <NetworkLocation>Work</NetworkLocation>
      </OOBE>
      <UserAccounts>
        <AdministratorPassword>
          <Value>{password}</Value>
          <PlainText>true</PlainText>
        </AdministratorPassword>
      </UserAccounts>
      <AutoLogon>
        <Enabled>true</Enabled>
        <Username>Administrator</Username>
        <Password>
          <Value>{password}</Value>
          <PlainText>true</PlainText>
        </Password>
        <LogonCount>5</LogonCount>
      </AutoLogon>
      <FirstLogonCommands>
{first_logon}
      </FirstLogonCommands>
    </component>
  </settings>
</unattend>
"""
