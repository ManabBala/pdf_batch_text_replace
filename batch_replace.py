import os
import subprocess

# Directory containing the PDF files
input_directory = "input"
output_directory = "output"

# Ensure the output directory exists
os.makedirs(output_directory, exist_ok=True)

# Text to search and replace
search_text = "put your text here that you want to replace"
replace_text = "put your replacement text here"

# Path to the Python interpreter in your virtual environment
python_path = "venv/bin/python"  # On Windows, use "path/to/venv/Scripts/python.exe"

# Path to the pypdf_strreplace.py script
script_path = "pypdf_strreplace.py"


# Function to create the same directory structure in the output folder
def ensure_output_subdir(input_path, output_base_dir):
    relative_path = os.path.relpath(input_path, input_directory)
    output_subdir = os.path.join(output_base_dir, relative_path)
    os.makedirs(output_subdir, exist_ok=True)
    return output_subdir


# Iterate over all PDF files in the input directory and subdirectories
for root, dirs, files in os.walk(input_directory):
    for filename in files:
        if filename.endswith(".pdf"):
            input_file = os.path.join(root, filename)

            # Create corresponding output subdirectory
            output_subdir = ensure_output_subdir(root, output_directory)
            output_file = os.path.join(output_subdir, filename)

            # Construct the command
            command = [
                python_path,
                script_path,
                "--input",
                input_file,
                "--search",
                search_text,
                "--replace",
                replace_text,
                "--output",
                output_file,
            ]

            # Execute the command
            subprocess.run(command)

            print(f"Processed: {input_file} -> {output_file}")

print("Batch replacement complete!")
