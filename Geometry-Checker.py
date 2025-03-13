import streamlit as st
import pandas as pd
import geopandas as gpd
from shapely.geometry import shape
import json
import requests

### Title bit:

st.markdown("# :round_pushpin: :globe_with_meridians:")
st.markdown("# Facility List Geometry Checker")

with st.expander("**About this tool**", expanded=True):
    st.markdown('''
                This tool has been developed to perform data quality checks on geographic coordinates data. Simply choose your country, upload an Excel file containing coordinates, and click "Perform Data Quality Check" to get started. To learn more about how this works, select the box at the bottom of the page.  

                For more information, contact danielswatkins@gmail.com
                ''')

with st.expander("**What kind of a file can I use?**", expanded=False):
    st.write('''
                You can upload any CSV or Excel file containing health facility location data that is structured as follows:  
                      • Has one row per health facility, beginning in the first row below column headers.  
                      • Has separate columns for the facility name, latitude, longitude, and country. Note: do not worry about precise naming - you'll be able to identify the appropriate columns in the steps below.  
                      • Uses a decimal type for the latitude and longitude fields.  
                      To request a template, please contact danielswatkins@gmail.com
                ''')

### Country selector

col1, col2 = st.columns(2)

with col1:
    country_df = pd.read_csv('https://raw.githubusercontent.com/danielswatkins/Geometry-Checker/main/Country-ISO%20List.csv')
    st.markdown('### Select your country:')
    country_select = st.selectbox(label="country", options=country_df['Country'], label_visibility="hidden", index=None)

if country_select:
    selected_row = country_df.loc[country_df['Country'] == country_select]
    selected_country = selected_row['Country'].values[0]
    selected_iso = selected_row['ISO'].values[0]
    request = requests.get('https://www.geoboundaries.org/api/current/gbOpen/' + selected_iso + '/ADM0').json()
    gdf = gpd.read_file(request['gjDownloadURL'])

    #### Streamlit needs to edit the data like this:
    country_gdf = gdf.copy()  # Create a copy to avoid modifying the original GDF
    country_gdf['geometry'] = country_gdf['geometry'].to_crs(epsg=4326)  # Ensure the geometry is in WGS84 (EPSG:4326)
    country_gdf = country_gdf.set_geometry('geometry')  # Set the geometry column
    country_gdf['geometry'] = country_gdf['geometry'].apply(lambda geom: json.dumps(geom.__geo_interface__))  # Convert geometry to GeoJSON

### Site list upload section
st.markdown("### Upload your file:")
uploaded_sites = st.file_uploader(label='Data File', type=['csv', 'xls', 'xlsx'],
                                      help="Upload a CSV or Excel file containing your sites. This should be the same file shared with USAID",
                                      label_visibility="hidden")


if uploaded_sites:
    st.markdown(">*Optional:* If you need to make any changes to your data, you can edit values directly in the table below. Take care to not make changes unless intended. For multiple changes, it is advisable to go back and edit the original file.")
    df = pd.read_excel(uploaded_sites)

    edited = st.data_editor(df, height=250)

    st.markdown("### Check your data:")

    with st.form("Select the corresponding columns:"):
        st.markdown("#### Select the corresponding columns:")
        col1, col2, col3 = st.columns(3)
        with col1:
            sitename_field_selection = st.selectbox("Site Name or ID ", edited.columns, key="sitename", index=None)
        with col2:
            latitude_field_selection = st.selectbox("Latitude Value (Y):", edited.columns, key="lat_entered", index=None)
        with col3:
            longitude_field_selection = st.selectbox("Longitude Value (X)", edited.columns, key="long_entered", index=None)

    # Check for missing values and display the warning before the submit button
        edited = edited.rename(columns={
            sitename_field_selection: 'Name',
            latitude_field_selection: 'lat',
            longitude_field_selection: 'lon'
        })
        missing_values = edited['lat'].isna().sum()
        if missing_values > 0:
            st.warning(f"**Warning**: A total of **{missing_values.sum()}** site(s) in the uploaded file are missing coordinates.")

        submitted = st.form_submit_button("Perform Data Quality Check")

        if submitted:
            edited['Name'] = edited['Name']
            edited['lat'] = edited['lat']
            edited['lon'] = edited['lon']

            sites_df = edited[['Name', 'lat', 'lon']]
            sites_gdf = gpd.GeoDataFrame(sites_df, geometry=gpd.points_from_xy(sites_df.lon, sites_df.lat), crs="EPSG:4326")
            sites_gdf = sites_gdf[sites_gdf['geometry'].notnull()]  # Remove rows with missing geometries
            sites_gdf['geometry'] = sites_gdf['geometry'].apply(lambda geom: json.dumps(geom.__geo_interface__) if geom else None)

            ### Applying geometry checks!
            st.markdown("#### Data Quality Check Results")

            def check_sites_within_country(country_gdf, sites_gdf):
                country_geometries = [shape(json.loads(geom)) for geom in country_gdf['geometry'].to_list() if geom] # Skip None values
                country_geometry = gpd.GeoSeries(country_geometries)
                sites_gdf['Within Country?'] = sites_gdf['geometry'].apply(lambda geom: shape(json.loads(geom)).within(country_geometry.unary_union) if geom else False)
                return sites_gdf

            country_check_result = check_sites_within_country(country_gdf, sites_gdf)
            country_check_result['Unique?'] = ~country_check_result['geometry'].duplicated(keep=False)

                ### specific values for precision
            decimal_categories = {range(0, 4): "Too Low", 4: "OK", range(5, 1000): "High",}
            def calculate_precision(value):
                if pd.notnull(value):
                    try:
                        precision = len(str(value).split('.')[1])
                        return next((v for k, v in decimal_categories.items() if (isinstance(k, int) and precision == k) or
                         (isinstance(k, range) and precision in k)), None)
                    except (IndexError, ValueError):
                        return None
                else:
                    return None

            country_check_result['Has Coordinates?'] = (country_check_result['lat'].notna() | country_check_result['lon'].notna())
            country_check_result['Precision (Lat)'] = country_check_result['lat'].apply(calculate_precision)
            country_check_result['Precision (Long)'] = country_check_result['lon'].apply(calculate_precision)

    ### specific values for percentages
            perc_within_country = round((country_check_result['Within Country?'].sum() / len(country_check_result['Within Country?'])) * 100, 2)
            perc_unique = round((country_check_result['Unique?'].sum() / len(country_check_result['Unique?'])) * 100, 2)
            perc_coordinates = round((country_check_result['Has Coordinates?'].sum() / len(country_check_result['Has Coordinates?'])) * 100, 2)
            high_count = ((country_check_result['Precision (Lat)'] == 'High') & (country_check_result['Precision (Long)'] == 'High')).sum()
            perc_precise = round(high_count / len(country_check_result['Name']) *100, 2)
    
    ### outputs on tabs
            tab1, tab2 = st.tabs(["Summary", "Full Results by Site"])
            with tab1:
                    col1, col2, col3, col4 = st.columns(4)
                    with col1:
                         st.metric(label="Sites have coordinates",
                                   value=f"{perc_coordinates}%",
                                   delta=f"{(country_check_result['Has Coordinates?'].sum())} / {len(country_check_result['Has Coordinates?'])} sites total", delta_color="off")
                    
                    with col2:
                        st.metric(label=f"Sites are in **{selected_country}**", 
                                value=f"{perc_within_country}%", 
                                delta=f"{(country_check_result['Within Country?'].sum())} / {len(country_check_result['Within Country?'])} sites total", delta_color="off")
                    with col3:
                        st.metric(label="Sites are unique", 
                                value=f"{perc_unique}%", 
                                delta=f"{(country_check_result['Unique?'].sum())} / {len(country_check_result['Unique?'])} sites total", delta_color="off")
                    with col4:
                        st.metric(label="High precision coordinates", 
                                value=f"{perc_precise}%", 
                                delta=f"{high_count} / {len(country_check_result['Unique?'])} sites total", delta_color="off")

            with tab2:
                    st.write("##### Full results by site:")
                    st.dataframe(country_check_result[['Name', 'Has Coordinates?', 'Within Country?', 'Unique?', 'Precision (Lat)', 'Precision (Long)']])

with st.expander("**How does this work?**"):
     st.write(f'''This webapp uses a series of automated processes to perform the following data quality checks on each site listed in the table:  
                      •  *Are the site's coordinates **within the selected country**?* This is done by comparing the latitude and longitude values against the outline of the shapefile, using boundaries for the selected countries from https://www.geoboundaries.org. If you think the results for this section are wrong, double-check against the country outline provided at the website.  
                      •  *Are the site coordinates provided **unique** to each site*, or does the dataset contain any duplicate values? This compares the uniqueness of each latitude-longitude pair, and identifies where those pairs appear more than once.  
                      •  *Are the provided coordinates **precise**?* Here, "Precise"" is defined as within 0.0001 decimal degrees, or 4 or more decimal places, while "High Precision"  is defined as 5 or more decimal places. Anything with 3 or fewer decimal places (e.g. 0.001) with be flagged as "Too Low", as the coordinates will only refer to a more general area than a specific building. Also note that, in general 6 or more decimal places will be *too precise* for a health facility location.
                  ''')
