"""
Advanced script to identify and fix instrument resource locks.
This script attempts to force-close locked resources and provides diagnostics.

WARNING: This script will attempt to close any open VISA resources.
Use with caution if other applications need the instruments.

Usage:
    python fix_instrument_locks.py
"""

import pyvisa
import sys
import time

def force_close_resources():
    """Attempt to force close any locked VISA resources."""
    print("=" * 60)
    print("Instrument Resource Lock Fixer")
    print("=" * 60)
    print()
    print("⚠️  WARNING: This will attempt to close all VISA resources.")
    print("   Make sure no other applications need the instruments.")
    print()
    
    response = input("Continue? (yes/no): ").strip().lower()
    if response not in ['yes', 'y']:
        print("Aborted.")
        return False
    
    print()
    print("1. Creating ResourceManager...")
    rm = None
    try:
        rm = pyvisa.ResourceManager()
        print(f"   ✅ ResourceManager created")
    except Exception as e:
        print(f"   ❌ Failed to create ResourceManager: {e}")
        return False
    
    print()
    print("2. Listing all resources...")
    try:
        resources = rm.list_resources()
        print(f"   Found {len(resources)} resource(s): {resources}")
    except Exception as e:
        print(f"   ❌ Failed to list resources: {e}")
        return False
    
    if not resources:
        print("   ℹ️  No resources found. Nothing to fix.")
        return True
    
    print()
    print("3. Attempting to open and immediately close each resource...")
    print()
    
    fixed = []
    failed = []
    
    for resource_name in resources:
        print(f"   Processing: {resource_name}")
        instrument = None
        
        try:
            # Try to open with a very short timeout
            instrument = rm.open_resource(resource_name)
            instrument.timeout = 100  # Very short timeout
            
            # Try to close it immediately
            try:
                instrument.close()
                print(f"      ✅ Successfully closed")
                fixed.append(resource_name)
            except Exception as e:
                print(f"      ⚠️  Opened but failed to close: {e}")
                failed.append((resource_name, f"Close failed: {e}"))
                
        except pyvisa.errors.VisaIOError as e:
            error_code = e.error_code
            if error_code == -1073807300:  # VI_ERROR_ALLOC
                print(f"      ❌ Still locked (VI_ERROR_ALLOC)")
                failed.append((resource_name, "VI_ERROR_ALLOC - Resource locked"))
            else:
                print(f"      ❌ Error: {e}")
                failed.append((resource_name, str(e)))
        except Exception as e:
            print(f"      ❌ Unexpected error: {e}")
            failed.append((resource_name, str(e)))
        
        # Small delay between attempts
        time.sleep(0.1)
        print()
    
    print("=" * 60)
    print("RESULTS")
    print("=" * 60)
    print(f"✅ Fixed/Closed: {len(fixed)}")
    for addr in fixed:
        print(f"   • {addr}")
    
    print(f"\n❌ Still locked: {len(failed)}")
    for addr, error in failed:
        print(f"   • {addr}: {error}")
    
    print()
    
    if failed:
        print("=" * 60)
        print("ADVANCED TROUBLESHOOTING")
        print("=" * 60)
        print()
        print("The following resources are still locked. Try these steps:")
        print()
        print("1. CHECK FOR RUNNING PROCESSES:")
        print("   • Open Task Manager (Ctrl+Shift+Esc)")
        print("   • Look for these processes:")
        print("     - LabVIEW.exe")
        print("     - TSPLink.exe")
        print("     - visa.exe")
        print("     - Python.exe (other instances)")
        print("     - Any application using VISA/GPIB")
        print("   • End these processes")
        print()
        print("2. CHECK DEVICE MANAGER:")
        print("   • Open Device Manager (Win+X, then Device Manager)")
        print("   • Look under 'GPIB' or 'Measurement devices'")
        print("   • Check for yellow warning icons")
        print("   • Right-click GPIB interface → 'Disable device'")
        print("   • Wait 5 seconds, then 'Enable device'")
        print()
        print("3. RESTART GPIB INTERFACE:")
        print("   • Physically disconnect GPIB cables")
        print("   • Wait 10 seconds")
        print("   • Reconnect GPIB cables")
        print("   • Wait for Windows to recognize devices")
        print()
        print("4. RESTART INSTRUMENTS:")
        print("   • Power OFF all instruments")
        print("   • Wait 30 seconds")
        print("   • Power ON instruments one by one")
        print("   • Wait for each to fully boot")
        print()
        print("5. RESTART WINDOWS:")
        print("   • If all else fails, restart Windows")
        print("   • This will clear all VISA resource locks")
        print()
        print("6. CHECK VISA BACKEND:")
        print("   • Open NI-MAX (if using NI-VISA)")
        print("   • Or Keysight Connection Expert (if using Keysight VISA)")
        print("   • Check for locked resources")
        print("   • Try to close them from there")
        print()
        
        return False
    else:
        print("✅ All resources are now available!")
        print("   You can now start the backend server.")
        return True

def check_processes():
    """Check for common processes that might lock instruments."""
    print()
    print("=" * 60)
    print("CHECKING FOR COMMON PROCESSES")
    print("=" * 60)
    print()
    print("Please manually check Task Manager for these processes:")
    print("  • LabVIEW.exe")
    print("  • TSPLink.exe")
    print("  • visa.exe or visa32.exe")
    print("  • Python.exe (other instances)")
    print("  • Any measurement/control software")
    print()
    print("If found, end these processes and try again.")

if __name__ == "__main__":
    try:
        success = force_close_resources()
        check_processes()
        
        if success:
            print()
            print("=" * 60)
            print("NEXT STEPS")
            print("=" * 60)
            print("1. Run: python check_instruments.py")
            print("2. If successful, start backend: python -m uvicorn app.main:app --reload --port 8080")
            sys.exit(0)
        else:
            print()
            print("⚠️  Some resources are still locked.")
            print("   Follow the troubleshooting steps above.")
            sys.exit(1)
            
    except KeyboardInterrupt:
        print("\n\nAborted by user.")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Fatal error: {e}")
        sys.exit(1)

