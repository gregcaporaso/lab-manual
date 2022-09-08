# Adapted from:
#  https://dash.plotly.com/live-updates
#  https://dash.plotly.com/dash-core-components/store

import datetime

import dash
from dash import dcc, html
import plotly
from dash.dependencies import Input, Output
import pandas as pd
from plotly.subplots import make_subplots
import plotly.express as px

import qwiic_bme280
import qwiic_sgp40
import pms5003



## Initialize data dashboard
_initial_data_store = pd.DataFrame(
        [],
        columns=['Temperature', 'Humidity', 'Pressure', 'VOC', 'PM1.0', 'PM2.5', 'PM10'])

timestamp_fmt = '%-d %B %Y at %-I:%M:%S %p.'
start_time = pd.Timestamp.now()
span_style = {'padding': '5px', 'fontSize': '16px'}
title_style = {'padding': '5px', 'fontSize': '20px'}

app = dash.Dash(
    __name__,
    title = "4CSCC sensor dashboard",
    update_title=None,
)

app.layout = html.Div([
    html.Div([
        dcc.Interval(
            id='interval-component',
            interval=5*1000, # in milliseconds
            n_intervals=0
        ),
        dcc.Store(
            id='sensor-data',
            data=_initial_data_store.to_json(date_format='iso', orient='split')
        ),
        html.H1('Data sensor live feed', style={'padding':'5px'}),
        html.Span('Server started on {}'.format(start_time.strftime(timestamp_fmt)), style=span_style),
        html.Br(),
        html.Span(
            ('Data is logged for a maximum period of 24 hours. Data older than 24 hours '
             'will be automatically discarded. Refreshing your browser will clear all '
             'previous data.' ), style=span_style),
        html.Hr()
    ]),
    html.Div([
        html.Div(id='live-text'),
        html.Hr(),
        html.Span("Temperature (F) 🌡️", style=title_style),
        dcc.Graph(id='live-temperature-graph', style={'background-color':'#f1f1f1'}),
        html.Hr(),
        html.Span("Percent relative humidity ☁️", style=title_style),
        dcc.Graph(id='live-humidity-graph',),
        html.Hr(),
        html.Span("Pressure (atmospheres) ⛰️", style=title_style),
        dcc.Graph(id='live-pressure-graph',),
        html.Hr(),
        html.Span("Volatile organic compounds (VOC) index 😷", style=title_style),
        html.Br(),
        html.Span(
            ("VOC index range is 0-500, with 100 representing "
             "typical air quality and larger numbers indicating "
             "worse air quality."), style=span_style),
        html.A(
            "Learn more about VOCs and VOC sensing here",
            href="https://bit.ly/3AE9qdE",
            target="_blank"),
        html.Span("."),
        dcc.Graph(id='live-voc-graph',),
        html.Hr(),
        html.Span("PM1.0 ✨", style=title_style),
        html.Br(),
        html.Span(
            ("ug/m3 of particles between 1.0um and 2.5um (ultrafine particles)."), style=span_style),
        html.A(
            "Learn more about particulate matter here",
            href="https://en.wikipedia.org/wiki/Particulates",
            target="_blank"),
        html.Span("."),
        dcc.Graph(id='live-pm1-graph',),
        html.Hr(),
        html.Span("PM2.5 🚭", style=title_style),
        html.Br(),
        html.Span(
            ("ug/m3 of particles between 2.5um and 10um (e.g. combustion particles, organic compounds, metals)."), style=span_style),
        html.A(
            "Learn more about particulate matter here",
            href="https://en.wikipedia.org/wiki/Particulates",
            target="_blank"),
        html.Span("."),
        dcc.Graph(id='live-pm2_5-graph',),
        html.Hr(),
        html.Span("PM10 🌻", style=title_style),
        html.Br(),
        html.Span(
            ("ug/m3 of particles larger than 10um (e.g. dust, pollen, mould spores)."), style=span_style),
        html.A(
            "Learn more about particulate matter here",
            href="https://en.wikipedia.org/wiki/Particulates",
            target="_blank"),
        html.Span("."),
        dcc.Graph(id='live-pm10-graph',),
     ]),
     html.Div([
        html.Hr(),
        html.Span("Developed by the ", style=span_style),
        html.A(
            "Four Corners Science and Computing Club (4CSCC)",
            href="https://gregcaporaso.github.io/4cscc-ln",
            target="_blank"),
        html.Span(". 🐢")
    ])
])


## Initialize data sensors
tph_sensor = qwiic_bme280.QwiicBme280()
voc_sensor = qwiic_sgp40.QwiicSGP40()
pm_sensor = pms5003.PMS5003()


def _check_tph_sensor():
    if not tph_sensor.is_measuring():
        try:
            started = tph_sensor.begin()
            # If we get here we are PROBABLY connected but idk maybe not
            if not started:
                print("BME 280 atmomspheric sensor failed to start. It may not be connected to the system.")
        # When I have the sensor completely unplugged I get an OS error
        except OSError:
            print("BME 280 atmospheric sensor does not appead to be connected")
            return None, None, None
        else:
            # discard first readings from the sensor as they tend to be unreliable
            _ = tph_sensor.temperature_fahrenheit
            _ = tph_sensor.pressure
            _ = tph_sensor.humidity

    return tph_sensor.temperature_fahrenheit, tph_sensor.humidity, tph_sensor.pressure / 101325 # convert Pascals to atmospheres 


def _check_voc_sensor():
    if not voc_sensor.is_measuring():
        print("VOC NOT MEASURING")
        try:
            started = voc_sensor.begin()
            # If we get here we are PROBABLY connected but idk maybe not
            if not started:
                print("SGP 40 VOC sensor failed to start. It may not be connected to the system.")
        # When I have the sensor completely unplugged I get an OS error
        except OSError:
            print("SGP 40 VOC sensor does not appead to be connected")
            return None
        else:
            # discard first readings from the sensor as they tend to be unreliable
            _ = voc_sensor.get_VOC_index()

    print("I GUESS IT IS MEASURING")
    return voc_sensor.get_VOC_index()


# This one has a different API from the other two
def _get_pms5003():
    try:
        pm_reading = pm_sensor.read()
        return pm_reading[3], pm_reading[4], pm_reading[5]
    except (pms5003.ChecksumMisMatchError, pms5003.ReadTimeoutError, PMS5003.SerialTimeoutError):
        print("Error reading from pms5003 sensor")
        return None, None, None


## Define callbacks and help functions
def _load_data(jsonified_data):
    df = pd.read_json(jsonified_data, orient='split')
    df.index = pd.DatetimeIndex(df.index)
    df.index.name = 'Time'
    return df


@app.callback(Output('sensor-data', 'data'),
        Input('sensor-data', 'data'),
        Input('interval-component', 'n_intervals'))
def collect_sensor_data(jsonified_data, n):
    df = _load_data(jsonified_data)
    df = df.last('86400S')

    dt = pd.Timestamp.now()
    tempF, humidity, pressure_atm = _check_tph_sensor()
    voc = _check_voc_sensor()
    pm1, pm2_5, pm10 = _get_pms5003()

    new_entry = pd.DataFrame([[tempF, humidity, pressure_atm, voc, pm1, pm2_5, pm10]],
                             index=[dt],
                             columns=['Temperature', 'Humidity', 'Pressure', 'VOC', 'PM1.0', 'PM2.5', 'PM10'])

    df = pd.concat([df, new_entry])
    return df.to_json(orient='split')


@app.callback(Output('live-text', 'children'),
              Input('sensor-data', 'data'))
def update_current_values(jsonified_data):
    df = _load_data(jsonified_data)
    most_recent_entry = df.tail(1)
    dt = pd.Timestamp(most_recent_entry.index[0]).strftime(timestamp_fmt)

    results = [
        html.Span('Most recent reading on {}'.format(dt), style=span_style),
        html.Br(),
        html.Span('Temperature: {0:0.2f} F'.format(most_recent_entry['Temperature'][0]), style=span_style),
        html.Span('Relative humidity: {0:0.2f}%'.format(most_recent_entry['Humidity'][0]), style=span_style),
        html.Span('Air pressure: {0:0.4f} atm'.format(most_recent_entry['Pressure'][0]), style=span_style),
        html.Span('VOC index: {0:0.2f}'.format(most_recent_entry['VOC'][0]), style=span_style),
        html.Span('PM1.0: {0}'.format(most_recent_entry['PM1.0'][0]), style=span_style),
        html.Span('PM2.5: {0}'.format(most_recent_entry['PM2.5'][0]), style=span_style),
        html.Span('PM10: {0}'.format(most_recent_entry['PM10'][0]), style=span_style),
    ]

    if most_recent_entry['Temperature'][0] >= 100:
        style = {'color':'red'}
        style.update(span_style)
        results.append(
            html.Span(dcc.Markdown(
                "**It's too hot!** Please remove heat source to avoid damaging computer or sensor! 🥵"),
                style=style)
        )

    return results


@app.callback(Output('live-temperature-graph', 'figure'),
              Output('live-humidity-graph', 'figure'),
              Output('live-pressure-graph', 'figure'),
              Output('live-voc-graph', 'figure'),
              Output('live-pm1-graph', 'figure'),
              Output('live-pm2_5-graph', 'figure'),
              Output('live-pm10-graph', 'figure'),
              Input('sensor-data', 'data'))
def update_graphs(jsonified_data):
    df = _load_data(jsonified_data)
    temp_fig = px.line(
            df,
            x=df.index,
            y=df['Temperature'],
            range_y=(10,110),
            height=500)
    humidity_fig = px.line(
            df,
            x=df.index,
            y=df['Humidity'],
            range_y=(0,100),
            height=500)
    pressure_fig = px.line(
            df,
            x=df.index,
            y=df['Pressure'],
            range_y=(0,2),
            height=500)
    voc_fig = px.line(
            df,
            x=df.index,
            y=df['VOC'],
            range_y=(0,500),
            height=500)
    pm1_fig = px.line(
            df,
            x=df.index,
            y=df['PM1.0'],
            height=500)
    pm2_5_fig = px.line(
            df,
            x=df.index,
            y=df['PM2.5'],
            height=500)
    pm10_fig = px.line(
            df,
            x=df.index,
            y=df['PM10'],
            height=500)
    return temp_fig, humidity_fig, pressure_fig, voc_fig, pm1_fig, pm2_5_fig, pm10_fig


if __name__ == '__main__':
    app.run_server(host="0.0.0.0", debug=True)
