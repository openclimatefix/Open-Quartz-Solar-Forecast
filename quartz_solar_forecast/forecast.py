from datetime import datetime, timedelta
from typing import Optional

import pandas as pd

from quartz_solar_forecast.data import get_nwp, make_pv_data
from quartz_solar_forecast.forecasts import forecast_v1_tilt_orientation, TryolabsSolarPowerPredictor
from quartz_solar_forecast.pydantic_models import PVSite


def predict_ocf(
    site: PVSite,
    model=None,
    ts: Optional[datetime | str] = None,
    nwp_source: str = "icon",
    access_token: Optional[str] = None,
    enphase_system_id: Optional[str] = None,
    solis_data: Optional[pd.DataFrame] = None,
    givenergy_data: Optional[pd.DataFrame] = None
):
    """
    Run the forecast with the gb model, which can take tilt and orientation as inputs
    
    :param site: the PV site
    :param model: the model to use for prediction
    :param ts: the timestamp of the site. If None, defaults to the current timestamp rounded down to 15 minutes.
    :param nwp_source: the nwp data source. Either "gfs" or "icon". Defaults to "icon"
    :param access_token: optional access token for API calls
    :param enphase_system_id: optional Enphase system ID
    :param solis_data: optional pre-fetched Solis data
    :param givenergy_data: optional pre-fetched GivEnergy data
    :return: The PV forecast of the site for time (ts) for 48 hours
    """
    if ts is None:
        ts = pd.Timestamp.now().round("15min")

    if isinstance(ts, str):
        ts = datetime.fromisoformat(ts)

    # make pv and nwp data from nwp_source
    nwp_xr = get_nwp(site=site, ts=ts, nwp_source=nwp_source)
    pv_xr = make_pv_data(
        site=site,
        ts=ts,
        access_token=access_token,
        enphase_system_id=enphase_system_id,
        solis_data=solis_data,
        givenergy_data=givenergy_data
    )

    # load and run models
    pred_df = forecast_v1_tilt_orientation(nwp_source, nwp_xr, pv_xr, ts, model=model)

    return pred_df

def predict_tryolabs(
    site: PVSite, ts: datetime | str = None):
    """
    Run the forecast with the xgb model
    
    :param site: the PV site
    :param ts: the timestamp of the site. If None, defaults to the current timestamp rounded down to 15 minutes.
    :return: The PV forecast of the site for time (ts) for 48 hours
    """

    # instantiate class to make predictions
    solar_power_predictor = TryolabsSolarPowerPredictor()
    
    # set start and end time, if no time is given use current time
    if ts is None:
        start_date = pd.Timestamp.now().strftime("%Y-%m-%d")
        start_time = pd.Timestamp.now().round(freq='h')
    else:
        start_date = pd.Timestamp(ts).strftime("%Y-%m-%d")
        start_time = pd.Timestamp(ts).round(freq='h')

    end_time = start_time + pd.Timedelta(hours=48)
    start_date_datetime = datetime.strptime(start_date, "%Y-%m-%d")

    # Check if the start date is more than 3 months ago
    three_months_ago = datetime.today() - timedelta(days=3 * 30)

    if start_date_datetime < three_months_ago:
        print(
            f"Start date ({start_date}) is more than 3 months ago, no",
            "forecast data available.",
        )
    else:
        # download the model from google drive and decompress if necessary
        solar_power_predictor.load_model()
        # make predictions
        predictions = solar_power_predictor.predict_power_output(
            latitude=site.latitude,
            longitude=site.longitude,
            start_date=start_date,
            kwp=site.capacity_kwp,
            orientation=site.orientation,
            tilt=site.tilt,
        )

        # postprocessing of the dataframe
        predictions = predictions[
            (predictions["date"] >= start_time) & (predictions["date"] < end_time)
        ]
        predictions = predictions.reset_index(drop=True)
        predictions.set_index("date", inplace=True)
        print("Predictions finished.")
        return predictions


def run_forecast(
    site: PVSite,
    model: str = "gb",
    ts: Optional[datetime | str] = None,
    nwp_source: str = "icon",
    access_token: Optional[str] = None,
    enphase_system_id: Optional[str] = None,
    solis_data: Optional[pd.DataFrame] = None,
    givenergy_data: Optional[pd.DataFrame] = None
) -> pd.DataFrame:
    """
    Predict solar power output for a given site using a specified model.

    :param site: the PV site
    :param model: the model to use for prediction, choose between "gb" and "xgb",
                    by default "gb" is used
    :param ts: the timestamp of the site. If None, defaults to the current timestamp rounded down to 15 minutes.
    :param nwp_source: the nwp data source. Either "gfs" or "icon". Defaults to "icon" 
                       (only relevant if model=="gb")
    :param access_token: optional access token for API calls
    :param enphase_system_id: optional Enphase system ID
    :param solis_data: optional pre-fetched Solis data
    :param givenergy_data: optional pre-fetched GivEnergy data
    :return: The PV forecast of the site for time (ts) for 48 hours
    """

    if model == "gb":
        return predict_ocf(
            site=site,
            model=None,
            ts=ts,
            nwp_source=nwp_source,
            access_token=access_token,
            enphase_system_id=enphase_system_id,
            solis_data=solis_data,
            givenergy_data=givenergy_data
        )
              
    elif model == "xgb":
        return predict_tryolabs(site, ts)
    
    else:  
        raise ValueError(f"Unsupported model: {model}. Choose between 'xgb' and 'gb'")
