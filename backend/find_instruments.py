"""
Utility script to discover and list all available instruments on the GPIB bus.
Run this script to find the correct addresses for your instruments.

Usage:
    python find_instruments.py
"""

import pyvisa
import sys

def find_instruments():
    """Discover all available instruments on the GPIB bus."""
    print("=" * 60)
    print("Instrument Discovery Tool")
    print("=" * 60)
    print()
    
    try:
        # Create a resource manager
        rm = pyvisa.ResourceManager()
        print(f"PyVISA Resource Manager: {rm}")
        print(f"Backend: {rm.list_resources()}")
        print()
        
        # Check for common issues
        print("Checking for common issues...")
        print("1. Make sure all instruments are powered on")
        print("2. Close any other applications using the instruments (LabVIEW, TSPLink, etc.)")
        print("3. If the backend server is running, stop it before running this script")
        print()
        
        # List all available resources
        resources = rm.list_resources()
        
        if not resources:
            print("❌ No instruments found!")
            print("\nPossible reasons:")
            print("  1. Instruments are not powered on")
            print("  2. GPIB/USB cables are not connected")
            print("  3. Drivers are not installed (NI-VISA, Keysight IO Libraries, etc.)")
            print("  4. GPIB interface card is not recognized")
            return
        
        print(f"✅ Found {len(resources)} instrument(s):")
        print()
        
        instruments = []
        
        for i, resource_name in enumerate(resources, 1):
            print(f"{i}. Resource: {resource_name}")
            
            # Try to open and identify the instrument
            instrument = None
            try:
                instrument = rm.open_resource(resource_name)
                instrument.timeout = 2000  # 2 second timeout
                
                # Try to identify the instrument
                try:
                    # Send *IDN? query (standard SCPI command)
                    idn = instrument.query("*IDN?")
                    print(f"   IDN Response: {idn.strip()}")
                    
                    # Parse manufacturer and model
                    parts = idn.strip().split(',')
                    if len(parts) >= 2:
                        manufacturer = parts[0].strip()
                        model = parts[1].strip()
                        print(f"   Manufacturer: {manufacturer}")
                        print(f"   Model: {model}")
                        
                        # Try to identify instrument type
                        instrument_type = "Unknown"
                        if "2182" in model.upper() or "2182" in idn.upper():
                            instrument_type = "Keithley 2182A (Nanovoltmeter)"
                        elif "2700" in model.upper() or "2700" in idn.upper():
                            instrument_type = "Keithley 2700 (Multimeter/Scanner)"
                        elif "6221" in model.upper() or "6221" in idn.upper():
                            instrument_type = "Keithley 6221 (SourceMeter)"
                        elif "PK160" in model.upper() or "PK160" in idn.upper():
                            instrument_type = "PK160 (Power Supply)"
                        elif "KEITHLEY" in manufacturer.upper():
                            instrument_type = f"Keithley {model}"
                        
                        instruments.append({
                            'address': resource_name,
                            'manufacturer': manufacturer,
                            'model': model,
                            'type': instrument_type,
                            'idn': idn.strip()
                        })
                        print(f"   Type: {instrument_type}")
                    
                except Exception as e:
                    print(f"   ⚠️  Could not query *IDN?: {str(e)}")
                    instruments.append({
                        'address': resource_name,
                        'manufacturer': 'Unknown',
                        'model': 'Unknown',
                        'type': 'Unknown',
                        'idn': 'N/A'
                    })
                
            except Exception as e:
                print(f"   ❌ Could not open resource: {str(e)}")
                # Check if it's a resource allocation error
                if "VI_ERROR_ALLOC" in str(e) or "-1073807300" in str(e):
                    print(f"   💡 Tip: This error often means:")
                    print(f"      - Another process is using this instrument")
                    print(f"      - Previous connections weren't closed properly")
                    print(f"      - Try closing other applications using the instruments")
                    print(f"      - Restart the Python interpreter/backend server")
            finally:
                # Always close the instrument if it was opened
                if instrument is not None:
                    try:
                        instrument.close()
                    except:
                        pass
            
            print()
        
        # Summary
        print("=" * 60)
        print("SUMMARY - Recommended Addresses:")
        print("=" * 60)
        print()
        
        k2182a = None
        k2700 = None
        k6221 = None
        pk160 = None
        
        for inst in instruments:
            if "2182" in inst['model'].upper() or "2182" in inst['idn'].upper():
                k2182a = inst['address']
                print(f"Keithley 2182A: {inst['address']}")
            elif "2700" in inst['model'].upper() or "2700" in inst['idn'].upper():
                k2700 = inst['address']
                print(f"Keithley 2700:  {inst['address']}")
            elif "6221" in inst['model'].upper() or "6221" in inst['idn'].upper():
                k6221 = inst['address']
                print(f"Keithley 6221:  {inst['address']}")
            elif "PK160" in inst['model'].upper() or "PK160" in inst['idn'].upper():
                pk160 = inst['address']
                print(f"PK160:          {inst['address']}")
        
        print()
        print("=" * 60)
        print("Current configuration in instrument.py:")
        print("=" * 60)
        print(f"ADDR_2182A = \"{k2182a or 'GPIB0::7::INSTR'}\"")
        print(f"ADDR_2700  = \"{k2700 or 'GPIB0::16::INSTR'}\"")
        print(f"ADDR_6221  = \"{k6221 or 'GPIB0::18::INSTR'}\"")
        print(f"ADDR_PK160 = \"{pk160 or 'GPIB0::15::INSTR'}\"")
        print()
        
        if not k2182a or not k2700 or not pk160:
            print("⚠️  WARNING: Not all instruments were identified!")
            print("   You may need to manually check the addresses above.")
            print()
        
        # Clean up resource manager
        try:
            rm.close()
        except:
            pass
        
    except Exception as e:
        print(f"❌ Error: {str(e)}")
        print("\nTroubleshooting:")
        print("  1. Make sure PyVISA is installed: pip install pyvisa")
        print("  2. Install VISA backend:")
        print("     - Windows: Install NI-VISA or Keysight IO Libraries Suite")
        print("     - Linux: Install pyvisa-py backend or libvisa")
        print("  3. Check that instruments are powered on and connected")
        sys.exit(1)

if __name__ == "__main__":
    find_instruments()

