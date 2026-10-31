import sys

try:
    print("256 bit ANSI Standrad colors 0-15")
    for col in range(0, 15):
        print (f"\x1b[5;38;5;{col}mThis is a test string with color {col}\x1b[0m", end = '\t')
        print (f"\x1b[48;5;{col}mThis is a test string with background color {col}\x1b[0m")
    print("\n256 bit ANSI Standrad colors 16-231")
    for col in range(16, 231):
        print (f"\x1b[5;38;5;{col}mThis is a test string with color {col}\x1b[0m", end = '\t')
        print (f"\x1b[48;5;{col}mThis is a test string with background color {col}\x1b[0m")
    print("\n256 bit ANSI Standrad colors 231-255 - Gray scale ramp")
    for col in range(231, 255):
        print (f"\x1b[5;38;5;{col}mThis is a test string with color {col}\x1b[0m", end = '\t')
        print (f"\x1b[48;5;{col}mThis is a test string with background color {col}\x1b[0m")
except KeyboardInterrupt:
    print ("\nExiting color test.")

sys.exit(0)