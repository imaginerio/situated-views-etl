import re
from dagster import op, In, Out
import pandas as pd


@op(
    ins={"jstor": In(root_manager_key="jstor_root", dagster_type=pd.DataFrame)},
    out={"metadata": Out(io_manager_key="pandas_csv")},
)
def append_jstor(context, jstor, metadata):
    jstor = jstor.rename(columns=lambda x: re.sub(r"\[[0-9]*\]", "", x))
    jstor.drop(columns="Creator", inplace=True)
    jstor = jstor.rename(
        columns={
            "Title original Language": "Title",
            "Creator (Shared Shelf Names)": "Creator",
            "First Display Year": "First Year",
            "Last Display Year": "Last Year",
        }
    )
    jstor["Document ID"] = jstor["SSID"]
    jstor["Collections"] = jstor["Collections"].str.replace("|", "||")
    metadata = metadata.append(jstor)

    metadata_new = metadata[
        [
            "Document ID",
            "SSID",
            "Title",
            "Creator",
            "Description (English)",  # vazio ou string fixa feito no cumulus ok
            "Description (Portuguese)",
            "Date",
            "First Year",
            "Last Year",
            "Type",
            "Collections",
            "Provider",
            "Document URL",  # url do portals
            "Materials",
            "Fabrication Method",
            "Rights",  # vazio ou string fixa feito no cumulus ok
            "License",  # vazio ou string fixa feito no cumulus ok
            "Required Statement",  # vazio ou string fixa feito no cumulus ok
            "Width (mm)",
            "Height (mm)",
            "Latitude",  # camera
            "Longitude",  # camera
            "Depicts",  # wikidata
            "Wikidata ID",  # id do wikiddata
            "Smapshot ID",  # vazio
            "Media URL",  # Media URL do images
        ]
    ]

    # metadata_new["SSID"] = metadata_new["SSID"].astype(np.float).astype("Int32")
    return metadata_new.set_index("Document ID")
