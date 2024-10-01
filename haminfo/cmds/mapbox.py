import click
from oslo_config import cfg
from rich.console import Console
import secrets
import time

import haminfo
from haminfo.main import cli
from haminfo import cli_helper



@cli.command()
@cli_helper.add_options(cli_helper.common_options)
@click.option('--disable-spinner', is_flag=True, default=False,
              help='Disable all terminal spinning wait animations.')
@click.option(
    "--force",
    "force",
    show_default=True,
    is_flag=True,
    default=False,
    help="Used with -i, means don't wait for a DB wipe",
)
@click.option(
    "--id",
    default="",
    help="The mapbox datasource ID"
)
@click.option(
    "--show",
    is_flag=True,
    default=False,
    help="List all the existing items in mapbox dataset"
)
@click.pass_context
@cli_helper.process_standard_options
def mapbox(ctx, disable_spinner, force, id, show):
    """Update some DB records?"""
    console = Console()


    ds = Datasets()
    console.print(ds.baseuri)
    if show:
        if not id:
            console.print("shit")
            sys.exit(-1)
        entries = ds.read_dataset(id).json()
        console.print(entries)
        # for entry in entries:
        #    console.print(entry)
        # Show the features
        features = ds.list_features(id)
        if features.status_code == 200:
            f_json = features.json()
            console.print(f_json)
    else:
        # Load all the requests and put it in the dataset
        db_session = db.setup_session()
        session = db_session()

        with console.status("Fetching Records") as status:
            with session:
                query = db.find_requests(session, 0)
                console.print(query)
                count = query.count()
                for req in query:
                    status.update(f"Fetching {count} Records")
                    point = Point((req.longitude, req.latitude))
                    _dict = req.to_dict()
                    _dict['created'] = str(_dict['created'])
                    marker = Feature(geometry=point,
                                     id=str(req.id),
                                     properties=_dict
                                     )
                    console.print(marker)
                    result = ds.update_feature(id, str(req.id), marker)
                    if result.status_code == 200:
                        console.print(result.json())
                    count -= 1
