"""
Quick diagnostic script to check instrument connections and identify issues.
Run this before starting the backend server to ensure instruments are available.

Usage:
    python check_instruments.py
"""

import pyvisa
import sys

def check_instruments():
    """Check instrument availability and provide diagnostics."""
    print("=" * 60)
    print("Instrument Connection Diagnostic Tool")
    print("=" * 60)
    print()
    
    try:
        # Create resource manager
        print("1. Creating PyVISA ResourceManager...")
        rm = pyvisa.ResourceManager()
        print(f"   ✅ ResourceManager created: {rm}")
        print()
        
        # List resources
        print("2. Scanning for available instruments...")
        resources = rm.list_resources()
        print(f"   Found {len(resources)} resource(s): {resources}")
        print()
        
        if not resources:
            print("❌ No instruments found!")
            print("\nTroubleshooting:")
            print("  • Check that instruments are powered on")
            print("  • Verify GPIB/USB cables are connected")
            print("  • Ensure VISA drivers are installed (NI-VISA or Keysight IO Libraries)")
            print("  • Check Device Manager for instrument recognition")
            return False
        
        # Check each resource
        print("3. Testing each instrument connection...")
        print()
        
        available = []
        unavailable = []
        
        for resource_name in resources:
            print(f"   Testing: {resource_name}")
            instrument = None
            try:
                instrument = rm.open_resource(resource_name)
                instrument.timeout = 1000  # 1 second timeout for quick check
                
                # Try to query IDN
                try:
                    idn = instrument.query("*IDN?")
                    print(f"      ✅ Available - IDN: {idn.strip()}")
                    available.append(resource_name)
                except Exception as e:
                    print(f"      ⚠️  Opened but query failed: {str(e)}")
                    unavailable.append((resource_name, str(e)))
                
            except pyvisa.errors.VisaIOError as e:
                error_code = e.error_code
                error_msg = str(e)
                print(f"      ❌ Cannot open: {error_msg}")
                
                if error_code == -1073807300:  # VI_ERROR_ALLOC
                    print(f"         💡 VI_ERROR_ALLOC detected!")
                    print(f"         This usually means:")
                    print(f"         • Another process is using this instrument")
                    print(f"         • Previous connections weren't closed")
                    print(f"         • Try closing LabVIEW, TSPLink, or other apps")
                    print(f"         • Restart the backend server if it's running")
                
                unavailable.append((resource_name, error_msg))
            except Exception as e:
                print(f"      ❌ Error: {str(e)}")
                unavailable.append((resource_name, str(e)))
            finally:
                if instrument is not None:
                    try:
                        instrument.close()
                    except:
                        pass
            
            print()
        
        # Summary
        print("=" * 60)
        print("SUMMARY")
        print("=" * 60)
        print(f"✅ Available instruments: {len(available)}")
        for addr in available:
            print(f"   • {addr}")
        
        print(f"\n❌ Unavailable instruments: {len(unavailable)}")
        for addr, error in unavailable:
            print(f"   • {addr}: {error}")
        
        print()
        
        if unavailable:
            print("RECOMMENDATIONS:")
            print("  1. Close any other applications using the instruments")
            print("  2. If the backend server is running, stop it completely")
            print("  3. Restart the Python interpreter")
            print("  4. Check Windows Device Manager for instrument status")
            print("  5. Try unplugging and replugging GPIB/USB cables")
            print("  6. Restart the instruments (power cycle)")
            return False
        else:
            print("✅ All instruments are available and ready to use!")
            return True
        
    except Exception as e:
        print(f"❌ Fatal error: {str(e)}")
        print("\nTroubleshooting:")
        print("  • Verify PyVISA is installed: pip install pyvisa")
        print("  • Check VISA backend installation")
        print("  • Ensure instruments are powered on")
        sys.exit(1)
    finally:
        try:
            rm.close()
        except:
            pass

if __name__ == "__main__":
    success = check_instruments()
    sys.exit(0 if success else 1)

