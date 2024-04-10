import argparse
import os

from ..config import *
from ..utils.helpers import get_metadata_changes, summarize
from ..utils.logger import logger
from . import iiif, viewcones


def main():
    # Compare data, overwrite current data file if there are changes and return those changes
    metadata = get_metadata_changes(CURRENT_JSTOR, NEW_JSTOR)
    # Filter changes in published items
    metadata = metadata.loc[metadata["Status"] == "In imagineRio"]

    # Update viewcones if any
    if any(file for file in os.listdir(KMLS_IN) if file != ".gitkeep"):
        viewcones_info = viewcones.update()
    else:
        logger.info("No KMLs to process, skipping")
        viewcones_info = None

    # Update manifests if published items data has changed
    if metadata.empty:
        logger.info("No metadata changes detected, exiting")
        manifest_info = None
    else:
        manifest_info = iiif.update_manifests(metadata)

    if viewcones_info or manifest_info:
        summary = summarize(viewcones_info, manifest_info)
        logger.info(summary)


if __name__ == "__main__":
    main()
