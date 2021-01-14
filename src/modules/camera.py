import os

import geopandas as gpd
import pandas as pd


def load(csv, geojson):
    try:
        cameras = load_camera(csv)

        cones = load_cones(geojson)

        df = pd.merge(cameras, cones, on=["id"], how="left", validate="one_to_one")

        return df

    except Exception as e:
        print(str(e))


def load_camera(path):
    """
    Return dataframe from camera.csv
    """

    # read csv
    camera = pd.read_csv(path)

    # rename columns
    camera = camera.rename(columns={"name": "id", "long": "lng",})

    # list and drop duplicates
    # duplicated_kmls = camera.duplicated(subset="id")
    # if duplicated_kmls["id"].any == True:
    #     duplicated_kmls.to_csv("data-out/duplicated-kmls.csv")
    # camera = camera.drop_duplicates(subset="id", keep="last")

    return camera


def load_cones(path):
    """
    Return geodataframe from camera.geojson
    """

    # read geojson
    viewcone = gpd.read_file(path)

    # rename columns
    viewcone = viewcone.rename(columns={"name": "id",})

    # subset by columns
    viewcone = viewcone[["id", "geometry"]]

    # remove duplicates
    viewcone = viewcone.drop_duplicates(subset="id", keep="last")

    return viewcone

if __name__ == "__main__":
    load(
                os.environ["CAMERA_CSV"], os.environ["CAMERA_GEOJSON"]
            )
