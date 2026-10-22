BY P800 A4 Thermal Printer Driver for Linux (CUPS)

Open-source driver, diagnostic, and calibration suite for the BY P800 A4 Thermal Printer (USB ID 0483:5743, ESC/POS raster GS v 0) on Linux distributions (tested and verified on Linux Mint, Ubuntu, and Debian).

Out of the box, this thermal printer only includes official drivers for Windows. This repository bridges that gap by providing a native CUPS filter, a customized PPD configuration, an automated installer, and a complete suite of engineering and calibration utilities.

📂 Project Architecture & File Overview

The repository is structured into two main categories: user deployment and low-level diagnostic tools.

1. Production / User-Facing Driver

install.sh: Automated deployment script that installs dependencies, compiles the C filter, validates the PPD, auto-discovers the printer's USB URI via CUPS, and sets up the print queue.

rastertop800.c: Core CUPS raster filter written in C. It handles color space conversion, custom PPD options, and implements Floyd-Steinberg error-diffusion dithering to achieve crisp photos and graphics on thermal paper.

p800.ppd: PostScript Printer Description file exposing native options in CUPS and Linux print dialogs (such as Dithering modes, Threshold levels, Left Offset, Page Trim, and Line Feed).

2. Engineering, Diagnostics & Calibration Tools

p800_probe.py: Interactive protocol probe script to test printer responses across multiple standards (ESC/POS status, TSPL, ZPL, CPCL, PCL).

p800_width_test.py: Geometric calibration pattern generator to determine the exact physical row width in bytes and dots, preventing image distortion or buffer overflows.

p800print.py: Standalone Python utility to directly stream processed images with custom dithering and banding controls.

⚙️ System Requirements

Operating System: Linux (Linux Mint, Ubuntu, Debian)

Print System: CUPS (Common Unix Printing System)

Build Tools: build-essential, libcups2-dev, cups-client

Python Dependencies: Python 3 with Pillow (python3-pil) for direct image printing utilities.

🚀 Quick Installation

Connect your printer via USB and ensure it is powered on.

Clone this repository and navigate to the folder:

git clone https://github.com/your-username/by-p800-linux-driver.git
cd by-p800-linux-driver


Make the installation script executable and run it with administrator privileges:

chmod +x install.sh
sudo ./install.sh


🖨️ Custom Printer Options (CUPS / PPD)

Once installed, you can configure printer behavior directly from the CUPS web interface (http://localhost:631) or via terminal using standard CUPS options (lp -o OptionName=Value):

P800Mode: Choose between Dither (Floyd-Steinberg for photos/screenshots) or Threshold (crisp black-and-white text and tables).

P800Threshold: Adjust darkness levels in threshold mode (T96, T128, T160, T192).

P800Offset: Horizontal alignment offset (Center or manual dot increments from L0 to L48).

P800Trim: Automatically trims trailing blank rows at the bottom of pages (True / False) to save thermal paper.

P800Feed: Configures final line feeds (Feed0, Feed6, Feed24, Feed48) after printing a page.

🛠️ Usage Examples (Python Utilities)

If you want to run the diagnostic or standalone printing tools directly:

Protocol Probing:

sudo cupsdisable P800
python3 p800_probe.py
sudo cupsenable P800


Width Calibration (e.g., trying 216 bytes / 1728 dots):

python3 p800_width_test.py 216


Direct Image Printing with Dithering:

python3 p800print.py sample.png --width-bytes 216 --band 128


📄 License

Distributed under the MIT License. See LICENSE for more information.
