import io
import os
import subprocess
from math import *
from typing import Collection, List, Mapping

import dagster as dg
import pandas as pd
import imgspy
import requests
from dotenv import load_dotenv
from IIIFpres import iiifpapi3
from IIIFpres.utilities import *
from PIL import Image
from requests.adapters import HTTPAdapter
from requests.api import get
from urllib3.util import Retry
from urllib.parse import urlsplit, urlunsplit

from solids.export import *

load_dotenv(override=True)

BUCKET = os.environ["BUCKET"]
iiifpapi3.BASE_URL = BUCKET + "/iiif/"
iiifpapi3.LANGUAGES = ["pt-BR", "en"]
Image.MAX_IMAGE_PIXELS = None


def file_exists(type, identifier):

    endpoint = BUCKET + "/iiif/{0}/{1}.json".format(identifier, type)

    retry_strategy = Retry(
        total=3,
        status_forcelist=[429, 500, 502, 503, 504],
        method_whitelist=["HEAD", "GET", "OPTIONS"],
    )

    adapter = HTTPAdapter(max_retries=retry_strategy)
    http = requests.Session()
    http.mount("https://", adapter)
    http.mount("http://", adapter)
    response = http.get(endpoint)

    if response.status_code == 200:
        return True
    else:
        return False


@dg.solid(output_defs=[dg.OutputDefinition(io_manager_key="iiif_manager")])
def tile_image(context, item):
    identifier = item["identifier"]

    if not file_exists("info", identifier) or context.mode_def.name == "test":
        img_data = requests.get(
            BUCKET + "/iiif/{0}/full/max/0/default.jpg".format(identifier)
        ).content

        img_path = f"iiif/{identifier}.jpg"

        if not os.path.exists("iiif"):
            os.mkdir("iiif")

        with open(img_path, "wb") as handler:
            handler.write(img_data)

        command = [
            "java",
            "-jar",
            "utils/iiif-tiler.jar",
            img_path,
            "-tile_size",
            "256",
            "-version",
            "3",
        ]

        process = subprocess.Popen(
            command,
        )
        process.communicate()
        os.remove(img_path)

        # TO-DO remove when java tiler gets updated with id as CLI argument
        with open("iiif/{0}/info.json".format(identifier), "r+") as f:
            info = json.load(f)
            info["id"] = info["id"].replace("http://localhost:8887", BUCKET)
            f.seek(0)  # rewind
            json.dump(info, f, indent=4)
            f.truncate()

        return [
            {"data": "iiif/{0}".format(identifier), "type": "path"},
        ]
    else:
        pass


@dg.solid(
    output_defs=[dg.OutputDefinition(io_manager_key="iiif_manager")],
)
def write_manifests(context, item):

    identifier = item["identifier"]

    # if not file_exists("manifest", identifier) or context.mode_def.name == "test":
    mapping = item["mapping"]
    item = item["row"]
    context.log.info("Processing: {0}".format(str(identifier)))

    # Get image sizes
    img_info = imgspy.info(
        BUCKET + "/iiif/{0}/full/max/0/default.jpg".format(identifier)
    )
    imgwidth, imgheight = img_info["width"], img_info["height"]

    # Logo
    logo = iiifpapi3.logo()
    logo.set_id(
        "https://aws1.discourse-cdn.com/free1/uploads/imaginerio/original/1X/8c4f71106b4c8191ffdcafb4edeedb6f6f58b482.png"
    )
    logo.set_format("image/png")
    logo.set_hightwidth(164, 708)

    # Header
    manifest = iiifpapi3.Manifest()
    manifest.set_id(
        extendbase_url="{0}/manifest.json".format(str(identifier).replace(" ", "_"))
    )
    manifest.add_label("pt-BR", item["Title"])

    # Metadata
    def map_wikidata(values_en, label_en, label_pt):
        en = []
        pt = []
        if not values_en:
            return None
        else:
            for value_en in values_en.split("||"):
                try:
                    url = "http://wikidata.org/wiki/{0}".format(
                        mapping.loc[value_en, "Wiki ID"]
                    )
                    value_pt = mapping.loc[value_en, "Label:pt"]
                    en.append(
                        '<a class="uri-value-link" target="_blank" href="{0}">{1}</a>'.format(
                            url, value_en
                        )
                    )
                    pt.append(
                        '<a class="uri-value-link" target="_blank" href="{0}">{1}</a>'.format(
                            url, value_pt
                        )
                    )
                except:
                    en.append(value_en)
                    pt.append(value_en)
                d = {"en": en, "pt": pt}

            return {
                "label_en": [label_en],
                "label_pt": [label_pt],
                "value_en": d["en"],
                "value_pt": d["pt"],
            }

    def set_metadata_field(manifest, field):
        if field:
            if "value" in field:
                value = {"none": field["value"]} if any(field["value"]) else None
            else:
                value = (
                    {"en": field["value_en"], "pt-BR": field["value_pt"]}
                    if any(field["value_pt"])
                    else None
                )

            if value:
                manifest.add_metadata(
                    entry={
                        "label": {
                            "en": field["label_en"],
                            "pt-BR": field["label_pt"],
                        },
                        "value": value,
                    }
                )
        else:
            pass

    # Values
    title = {
        "label_en": ["Title"],
        "label_pt": ["Título"],
        "value": [item["Title"]],
    }
    description = {
        "label_en": ["Description"],
        "label_pt": ["Descrição"],
        "value_en": [item["Description (English)"]]
        if item["Description (English)"]
        else [item["Description (Portuguese)"]],
        "value_pt": [item["Description (Portuguese)"]]
        if item["Description (Portuguese)"]
        else [item["Description (English)"]],
    }
    creator = {
        "label_en": ["Creator"],
        "label_pt": ["Autor"],
        "value": [item["Creator"]],
    }
    date = {
        "label_en": ["Date"],
        "label_pt": ["Data"],
        "value": [str(item["Date"])],
    }
    try:
        depicts = {
            "label_en": ["Depicts"],
            "label_pt": ["Retrata"],
            "value": [
                '<a class="uri-value-link" target="_blank" href="{0}">{1}</a>'.format(
                    *depicts.split(" ", maxsplit=1)
                )
                for depicts in item["Depicts"].split("||")
            ],
        }
    except:
        depicts = None
    type = map_wikidata(item["Type"], "Type", "Tipo")
    materials = map_wikidata(item["Materials"], "Materials", "Materiais")
    fabrication_method = map_wikidata(
        item["Fabrication Method"], "Fabrication Method", "Método de Fabricação"
    )
    width = {
        "label_en": ["Width (mm)"],
        "label_pt": ["Largura (mm)"],
        "value": [str(item["Width (mm)"])],
    }
    height = {
        "label_en": ["Height (mm)"],
        "label_pt": ["Altura (mm)"],
        "value": [str(item["Height (mm)"])],
    }

    fields = [
        title,
        description,
        creator,
        date,
        depicts,
        type,
        materials,
        fabrication_method,
        width,
        height,
    ]

    for field in fields:
        set_metadata_field(manifest, field)

    # Rights & Attribution
    if description["value_en"][0]:
        manifest.add_summary(language="en", text=description["value_en"][0])
        manifest.add_summary(language="pt-BR", text=description["value_pt"][0])

    required_statement = manifest.add_requiredStatement()
    if item["Attribution"]:
        required_statement_en = item["Attribution"] + "\nHosted by imagineRio"
        required_statement_pt = item["Attribution"] + "\nHospedado por imagineRio"
    else:
        required_statement_en = "Hosted by imagineRio"
        required_statement_pt = "Hospedado por imagineRio"
    required_statement.add_label("Hosting", "en")
    required_statement.add_value(required_statement_en, "en")
    required_statement.add_label("Hospedagem", "pt-BR")
    required_statement.add_value(required_statement_pt, "pt-BR")

    if item["License"].startswith("http"):
        manifest.set_rights(item["License"])
    elif item["Rights"].startswith("http"):
        manifest.set_rights(item["Rights"])
    else:
        manifest.set_rights("http://rightsstatements.org/vocab/CNE/1.0/")

    # Thumbnail
    thumbnail = iiifpapi3.thumbnail()
    thumb_width = int(imgwidth / 16)
    thumb_height = int(imgheight / 16)
    thumbnail.set_id(
        extendbase_url="{0}/full/{1},{2}/0/default.jpg".format(
            str(identifier).replace(" ", "_"), thumb_width, thumb_height
        )
    )
    thumbnail.set_hightwidth(thumb_height, thumb_width)
    manifest.add_thumbnail(thumbnailobj=thumbnail)

    # Homepage
    item_homepage = iiifpapi3.homepage()

    homepage_id = item["Source URL"] if item["Source URL"] else "https://null"

    try:
        item_homepage.set_id(objid=homepage_id)
    except:
        url_parts = list(urlsplit(homepage_id))
        url_parts[2:5] = ["", "", ""]
        new_url = urlunsplit(url_parts)
        item_homepage.set_id(objid=new_url)

    homepage_label = item["Source"] if item["Source"] else "imagineRio"
    item_homepage.add_label(language="none", text=homepage_label)
    item_homepage.set_type("Text")
    item_homepage.set_format("text/html")
    manifest.add_homepage(item_homepage)

    # See Also
    imaginerio_seealso = iiifpapi3.seeAlso()
    imaginerio_seealso.set_id(
        objid="https://www.imaginerio.org/map#{0}".format(identifier)
    )
    imaginerio_seealso.add_label(language="none", text="imagineRio")
    imaginerio_seealso.set_type("Text")
    manifest.add_seeAlso(imaginerio_seealso)

    if item["Wikidata ID"]:
        wikidata_seealso = iiifpapi3.seeAlso()
        wikidata_seealso.set_id(
            objid="https://www.wikidata.org/wiki/{0}".format(item["Wikidata ID"])
        )
        wikidata_seealso.add_label(language="none", text="Wikidata")
        wikidata_seealso.set_type("Text")
        # wikidata_seealso.set_format("text/html")
        manifest.add_seeAlso(wikidata_seealso)

    if item["Smapshot ID"]:
        smapshot_seealso = iiifpapi3.seeAlso()
        smapshot_seealso.set_id(
            objid="https://smapshot.heig-vd.ch/visit/{0}".format(item["Smapshot ID"])
        )
        smapshot_seealso.add_label(language="none", text="Smapshot")
        smapshot_seealso.set_type("Text")
        # smapshot_seealso.set_format("text/html")
        manifest.add_seeAlso(smapshot_seealso)

    # Provider
    item_provider = iiifpapi3.provider()
    item_provider.set_id("https://imaginerio.org/")
    item_provider.add_label("en", "imagineRio")
    item_provider.add_label("pt-BR", "imagineRio")
    item_provider.add_logo(logo)
    item_provider.add_homepage(item_homepage)
    manifest.add_provider(item_provider)

    # Canvas
    canvas = manifest.add_canvas_to_items()
    canvas.set_id(extendbase_url="canvas/p1")
    canvas.set_height(imgheight)
    canvas.set_width(imgwidth)
    canvas.add_label(language="none", text=identifier)

    annopage = canvas.add_annotationpage_to_items()
    annopage.set_id(extendbase_url="annotation-page/p1")
    annotation = annopage.add_annotation_to_items(target=canvas.id)
    annotation.set_id(extendbase_url="annotation/p1")
    annotation.set_motivation("painting")
    annotation.body.set_id(
        extendbase_url="{0}/full/max/0/default.jpg".format(identifier)
    )
    annotation.body.set_type("Image")
    annotation.body.set_format("image/jpeg")
    annotation.body.set_width(imgwidth)
    annotation.body.set_height(imgheight)
    s = annotation.body.add_service()
    s.set_id(extendbase_url="{0}/".format(identifier))
    s.set_type("ImageService3")
    s.set_profile("level0")

    # setup items to send to io_managers
    manifest_path = "iiif/{0}/manifest.json".format((identifier))
    manifest_obj = manifest.json_dumps(
        dumps_errors=False,
        ensure_ascii=False,
        context="http://iiif.io/api/presentation/3/context.json",
    )
    data = [{"data": manifest_obj, "key": manifest_path, "type": "json"}]

    # Logo
    logo = iiifpapi3.logo()
    logo.set_id(
        "https://aws1.discourse-cdn.com/free1/uploads/imaginerio/original/1X/8c4f71106b4c8191ffdcafb4edeedb6f6f58b482.png"
    )
    logo.set_format("image/png")
    logo.set_hightwidth(164, 708)

    for collection_name in item["Collections"].lower().split("||"):
        collection_path = "iiif/collection/{0}.json".format(collection_name)

        try:
            if context.mode_def.name == "test":
                collection = read_API3_json(collection_path)
            else:
                endpoint = BUCKET + "/" + collection_path
                retry_strategy = Retry(
                    total=3,
                    status_forcelist=[429, 500, 502, 503, 504],
                    method_whitelist=["HEAD", "GET", "OPTIONS"],
                )
                adapter = HTTPAdapter(max_retries=retry_strategy)
                http = requests.Session()
                http.mount("https://", adapter)
                http.mount("http://", adapter)
                collection_data = http.get(endpoint).json()
                collection = read_API3_json_dict(collection_data)

            # Deal with duplicates
            for item in collection.items:
                if "{0}/manifest".format(identifier) in item.id:
                    collection.items.remove(item)

        except Exception as e:
            print(e)
            print("Couldn't find collection: {0}. Creating...".format(collection_name))
            # Homepage
            collection_homepage = iiifpapi3.homepage()
            collection_homepage.set_id("https://imaginerio.org")
            collection_homepage.set_type("Text")
            collection_homepage.add_label("none", "imagineRio")
            collection_homepage.set_format("text/html")

            # Provider
            collection_provider = iiifpapi3.provider()
            collection_provider.set_id("https://imaginerio.org")
            collection_provider.add_label("en", "imagineRio")
            collection_provider.add_label("pt-BR", "imagineRio")
            collection_provider.add_logo(logo)
            collection_provider.add_homepage(collection_homepage)

            # Collection manifest
            collection = iiifpapi3.Collection()
            collection.set_id(
                extendbase_url="collection/{0}.json".format(collection_name)
            )
            collection.add_label("en", collection_name)
            collection.add_label("pt-BR", collection_name)
            collection.add_requiredStatement(
                label="Attribution",
                value="Hosted by imagineRio",
                language_l="en",
                language_v="en",
            )
            collection.add_requiredStatement(
                label="Attribution",
                value="Hospedado por imagineRio",
                language_l="pt-BR",
                language_v="pt-BR",
            )
            collection.set_rights("http://rightsstatements.org/vocab/CNE/1.0/")

            thumbnailobj = iiifpapi3.thumbnail()

            if collection_name == "all" or collection_name == "views":
                thumb_id = "0071824cx001-01/full/295,221/0/default.jpg"
                h, w = 221, 295
            elif collection_name == "plans":
                thumb_id = "10639297/full/259,356/0/default.jpg"
                h, w = 356, 259
            elif collection_name == "maps":
                thumb_id = "10643717/full/512,259/0/default.jpg"
                h, w = 259, 512
            elif collection_name == "aerials":
                thumb_id = "24879867/full/394,260/0/default.jpg"
                h, w = 260, 394
            elif collection_name == "mare":
                thumb_id = "31770323/full/188,125/0/default.jpg"
                h, w = 125, 188

            thumbnailobj.set_id(extendbase_url=thumb_id)
            thumbnailobj.set_hightwidth(h, w)
            collection.add_thumbnail(thumbnailobj=thumbnailobj)
            collection.add_provider(collection_provider)

        collection.add_manifest_to_items(manifest)

        # setup items to send to io_managers
        collection = collection.json_dumps(
            dumps_errors=False,
            ensure_ascii=False,
            context="http://iiif.io/api/presentation/3/context.json",
        )
        collections = {}
        collections["data"] = collection
        collections["key"] = collection_path
        collections["type"] = "json"
        data.append(collections)

        print("Collection updated: {0}".format(collection_name))
    # else:
    #    pass

    return data


@dg.solid(
    input_defs=[
        dg.InputDefinition("metadata", root_manager_key="metadata_root"),
        dg.InputDefinition("mapping", root_manager_key="mapping_root"),
    ],
    output_defs=[dg.DynamicOutputDefinition(dict)],
)
def get_items(context, metadata, mapping):
    ims = (
        (metadata["Latitude"].notna())
        & (metadata["Source URL"].notna())
        & (metadata["Media URL"].notna())
        & (metadata["First Year"].notna())
        & (metadata["Last Year"].notna())
    )
    jstor = metadata["SSID"].notna()
    metadata = metadata.loc[ims | jstor]
    metadata.fillna("", inplace=True)
    metadata.set_index("Source ID", inplace=True)
    mapping.set_index("Label:en", inplace=True)
    context.log.info(len(metadata))
    if context.mode_def.name == "test":
        metadata = pd.DataFrame(metadata.loc["007A5P4F03-006"]).T
    for identifier, item in metadata.iterrows():
        yield dg.DynamicOutput(
            value={"identifier": identifier, "row": item, "mapping": mapping},
            mapping_key=identifier.replace("-", "_"),
        )
