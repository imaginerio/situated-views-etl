import os
import shutil

import ffmpeg
import pandas as pd
from dotenv import load_dotenv

load_dotenv(override=True)

# path to images source on remote drive
SOURCE_PATH = input("Source folder:")

# list geolocated items
camera = pd.read_csv("./src/metadata/camera/camera.csv")
geolocated = list(camera["name"])


class Image:

    """Original image path. Attributes return id, jpg or tif extension."""

    def __init__(self, path):
        self.path = path
        self.jpg = str(os.path.split(self.path)[1].split(".")[0] + ".jpg")
        self.tif = str(os.path.split(self.path)[1])
        self.id = str(os.path.split(self.path)[1].split(".")[0])


def save_jpeg(image, output_folder, size=None, overwrite=False):
    """
    Saves jpg file using ffmpeg or returns None if file already exists and overwrite=False.
    If rescaling, "size" is the largest dimension in resulting image. 
    """

    # initialize ffmpeg
    stream = ffmpeg.input(image)
    # get filename for full path
    filename = (os.path.split(image)[1]).split(".")[0]
    # skip existing files when overwrite is False
    if not overwrite and os.path.exists(os.path.join(output_folder, f"{filename}.jpg")):
        print(f"{filename}.jpg already exists")
        return None
    # fit image within a square of size 'size'
    if size:
        stream = ffmpeg.filter(
            stream, "scale", size, size, force_original_aspect_ratio="decrease"
        )
    # destination folder
    stream = ffmpeg.output(
        stream, os.path.join(output_folder, filename) + ".jpg", **{"q": 0}
    )
    # run ffmpeg
    ffmpeg.run(stream, overwrite_output=True)


def file_handler(source_folder):
    """
    Returns list of original files in source folder according to internal requirements, 
    copies them to master and saves jpegs.
    """

    # create list of Image objects from source
    files = [
        Image(os.path.join(root, name))
        for root, dirs, files in os.walk(source_folder)
        for name in files
        if "FINALIZADAS" in root
        and name.endswith((".tif"))
        and not name.endswith(("v.tif"))
    ]

    # iterate over files at source
    for image in files:
        # copy original tiffs to /tiff/ or skip if already there
        if not os.path.exists(os.path.join(os.environ["TIFF"], image.tif)):
            shutil.copy2(image.path, os.environ["TIFF"])
        else:
            print(f"{image.tif} already in folder")
        # create hd and sd jpegs for geolocated items
        if image.id in geolocated:
            save_jpeg(
                os.path.join(os.environ["TIFF"], image.tif), os.environ["JPEG_HD"]
            )
            save_jpeg(
                os.path.join(os.environ["TIFF"], image.tif),
                os.environ["JPEG_SD"].replace(".", "src"),
                size=1000,
            )
        else:
            # create backlog with sd jpegs to be geolocated
            save_jpeg(
                os.path.join(os.environ["TIFF"], image.tif),
                os.environ["IMG_BACKLOG"],
                size=1000,
            )
    return files


def create_images_df(files):
    """Creates a dataframe with every image available and its alternate versions.
    "files" is a list of Image objects."""

    groups = []
    to_remove = []
    items = []

    # Find ids that contain other ids (secondary versions) and group them together
    for i, item in enumerate(files):
        # i = 0
        matched = []
        while i < len(files):
            if item.id in files[i].id:
                matched.append(files[i])
            # i += 1
        if len(matched) > 1:
            groups.append(matched)
        else:
            groups.append(item)

    # Remove secondary versions from main list
    for group in groups:
        if type(group) == list:
            to_remove += group[1:]

    groups = [item for item in groups if item not in to_remove]

    # Create list of dicts with all files available for each item
    for image in groups:
        if type(image) == list:
            # include just the 'master' version when others are available
            if image[0].id in geolocated:
                item = {
                    "id": image[0].id,
                    "img_hd": os.path.join(os.environ["CLOUD_PATH"], image[0].jpg),
                    "img_sd": os.path.join(os.environ["GITHUB_PATH"], image[0].jpg),
                }
                for i in image[1:]:
                    item[f"{i.id[-1]}"] = i.jpg
            else:
                # if item isn't geolocated, don't send to github or cloud
                item = {"id": image[0].id}
        else:
            if image.id in geolocated:
                item = {
                    "id": image.id,
                    "img_hd": os.path.join(os.environ["CLOUD_PATH"], image.jpg),
                    "img_sd": os.path.join(os.environ["GITHUB_PATH"], image.jpg),
                }
            else:
                # if item isn't geolocated, don't send to github or cloud
                item = {"id": image.id}
        items.append(item)

    images_df = pd.DataFrame(items)
    images_df.sort_values(by=["id"])

    return images_df


def main():
    """Execute all functions."""
    files = file_handler(SOURCE_PATH)

    print("Creating image dataframe...")

    images_df = create_images_df(files)

    print(images_df.head())

    images_df.to_csv("src/images/images.csv", index=False)


if __name__ == "__main__":
    main()
