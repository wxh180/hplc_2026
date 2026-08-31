# hplc_2026
interactive script for plotting Shimadzu hplc data
1. Save extract_hplc_trace_interactive.py somewhere easy to find, such as your Downloads folder.
2. Make sure you also have the LabSolutions exported .txt file on your Mac.
3. Open the Terminal app on your Mac.

Install Python if needed:

1. In Terminal, type python3 --version and press Return.
2. If you see a Python version, you can continue.
3. If not, install Python 3 from https://www.python.org/downloads/macos/ and then reopen Terminal.

Install the plotting packages:

1. In Terminal, run:
python3 -m pip install pandas matplotlib
2. Wait until installation finishes.

Run the script:

1. In Terminal, go to your Downloads folder:
cd ~/Downloads
2. Run the script:
python3 extract_hplc_trace_interactive.py

What the script will ask you:

• the path to your LabSolutions .txt file
• which chromatogram channel to plot
• the flow rate in mL/min
• the minimum and maximum elution volume to show
• the column type

Tips for the file path:

• The easiest way is to drag the .txt file from Finder into the Terminal window after the script asks for the file path.
• That will automatically paste the full path.

What you will get:

• a .tsv file with the extracted trace data
• a .png plot image
• a .pdf version of the plot
• a small metadata text file

Where the output goes:

• The script creates a new output folder next to the input .txt file.

If you get stuck:

• Take a screenshot of the Terminal window and send it back.
• The most common issues are:
  • Python not installed
  • pip packages not installed
  • wrong file path typed in manually
