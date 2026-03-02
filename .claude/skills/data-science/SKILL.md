---
name: data-science
description: Data science workflows with Jupyter, pandas, numpy, and visualization
version: 1.0.0
triggers:
  - jupyter
  - notebook
  - pandas
  - dataframe
  - data analysis
  - visualization
  - matplotlib
  - plotly
  - numpy
  - csv
  - data science
tags:
  - python
  - data
  - analysis
  - visualization
  - jupyter
---

# Data Science Development

## Summary

Data science workflows typically follow:
1. **Data Loading** - Read from CSV, databases, APIs
2. **Exploration** - Understand structure, distributions, missing values
3. **Cleaning** - Handle nulls, outliers, type conversions
4. **Analysis** - Compute statistics, find patterns
5. **Visualization** - Charts, plots, dashboards
6. **Export** - Save results, create reports

**Project structure:**
```
project/
├── data/
│   ├── raw/          # Original, immutable data
│   └── processed/    # Cleaned data
├── notebooks/        # Jupyter notebooks
├── src/              # Reusable code
│   ├── data.py       # Data loading/cleaning
│   ├── features.py   # Feature engineering
│   └── viz.py        # Visualization helpers
├── outputs/          # Figures, reports
└── requirements.txt
```

**Essential imports:**
```python
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns

# Set display options
pd.set_option('display.max_columns', 50)
pd.set_option('display.max_rows', 100)
plt.style.use('seaborn-v0_8-whitegrid')
```

## Details

### Data Loading

```python
# CSV
df = pd.read_csv('data.csv', parse_dates=['date_col'])

# Excel
df = pd.read_excel('data.xlsx', sheet_name='Sheet1')

# SQL
from sqlalchemy import create_engine
engine = create_engine('postgresql://user:pass@localhost/db')
df = pd.read_sql('SELECT * FROM users', engine)

# JSON
df = pd.read_json('data.json')

# Parquet (fast, columnar)
df = pd.read_parquet('data.parquet')
```

### Data Exploration

```python
# Basic info
df.info()
df.describe()
df.shape
df.columns.tolist()
df.dtypes

# Missing values
df.isnull().sum()
df.isnull().sum() / len(df) * 100  # Percentage

# Unique values
df['category'].nunique()
df['category'].value_counts()

# Sample
df.head(10)
df.sample(5)

# Correlations
df.corr(numeric_only=True)
```

### Data Cleaning

```python
# Handle missing values
df['col'].fillna(0, inplace=True)
df['col'].fillna(df['col'].mean(), inplace=True)
df.dropna(subset=['important_col'], inplace=True)

# Type conversions
df['date'] = pd.to_datetime(df['date'])
df['amount'] = pd.to_numeric(df['amount'], errors='coerce')
df['category'] = df['category'].astype('category')

# String cleaning
df['name'] = df['name'].str.strip().str.lower()

# Outlier removal
q1 = df['value'].quantile(0.25)
q3 = df['value'].quantile(0.75)
iqr = q3 - q1
df = df[(df['value'] >= q1 - 1.5*iqr) & (df['value'] <= q3 + 1.5*iqr)]

# Duplicates
df.drop_duplicates(subset=['id'], keep='first', inplace=True)
```

### Data Transformation

```python
# New columns
df['total'] = df['price'] * df['quantity']
df['year'] = df['date'].dt.year

# Apply functions
df['category'] = df['value'].apply(lambda x: 'high' if x > 100 else 'low')

# Grouping
summary = df.groupby('category').agg({
    'value': ['mean', 'sum', 'count'],
    'date': 'max'
}).reset_index()

# Pivot tables
pivot = df.pivot_table(
    values='amount',
    index='category',
    columns='month',
    aggfunc='sum',
    fill_value=0
)

# Merging
merged = pd.merge(df1, df2, on='id', how='left')
```

### Visualization

**Matplotlib basics:**
```python
fig, axes = plt.subplots(1, 2, figsize=(12, 5))

# Line plot
axes[0].plot(df['date'], df['value'], label='Value')
axes[0].set_xlabel('Date')
axes[0].set_ylabel('Value')
axes[0].legend()

# Bar chart
axes[1].bar(df['category'], df['count'])
axes[1].set_title('Counts by Category')

plt.tight_layout()
plt.savefig('outputs/analysis.png', dpi=150)
plt.show()
```

**Seaborn for statistical plots:**
```python
# Distribution
sns.histplot(df['value'], kde=True)

# Scatter with regression
sns.regplot(x='feature1', y='target', data=df)

# Categorical
sns.boxplot(x='category', y='value', data=df)
sns.violinplot(x='category', y='value', data=df)

# Heatmap
sns.heatmap(df.corr(), annot=True, cmap='coolwarm', center=0)

# Pairplot
sns.pairplot(df[['col1', 'col2', 'col3', 'target']], hue='target')
```

**Plotly for interactive:**
```python
import plotly.express as px

fig = px.scatter(df, x='x', y='y', color='category', size='value',
                 hover_data=['name'], title='Interactive Scatter')
fig.show()
fig.write_html('outputs/interactive.html')
```

## Advanced

### Time Series

```python
# Set datetime index
df = df.set_index('date')
df = df.sort_index()

# Resampling
daily = df.resample('D').mean()
monthly = df.resample('M').sum()

# Rolling windows
df['rolling_mean'] = df['value'].rolling(window=7).mean()
df['rolling_std'] = df['value'].rolling(window=7).std()

# Lag features
df['value_lag1'] = df['value'].shift(1)
df['value_diff'] = df['value'].diff()

# Seasonal decomposition
from statsmodels.tsa.seasonal import seasonal_decompose
result = seasonal_decompose(df['value'], period=12)
result.plot()
```

### Performance Optimization

```python
# Use appropriate dtypes
df['id'] = df['id'].astype('int32')  # vs int64
df['category'] = df['category'].astype('category')

# Chunked reading for large files
chunks = pd.read_csv('huge.csv', chunksize=100000)
result = pd.concat([process_chunk(chunk) for chunk in chunks])

# Query for faster filtering
df.query('category == "A" and value > 100')

# Vectorized operations (fast)
df['result'] = np.where(df['value'] > 100, 'high', 'low')

# Avoid iterrows (slow)
# Instead use: apply, vectorized ops, or itertuples
```

### Jupyter Best Practices

```python
# Magic commands
%matplotlib inline
%load_ext autoreload
%autoreload 2  # Auto-reload imported modules

# Suppress warnings
import warnings
warnings.filterwarnings('ignore')

# Memory usage
df.info(memory_usage='deep')

# Execution time
%%time
df.groupby('category').mean()
```

### Reproducibility

```python
# Set random seed
np.random.seed(42)

# Document environment
# !pip freeze > requirements.txt

# Version data
from datetime import datetime
df.to_parquet(f'data/processed/data_{datetime.now():%Y%m%d}.parquet')
```

## Resources

- [Pandas Docs](https://pandas.pydata.org/docs/)
- [NumPy Docs](https://numpy.org/doc/)
- [Matplotlib Docs](https://matplotlib.org/stable/)
- [Seaborn Docs](https://seaborn.pydata.org/)
- [Plotly Docs](https://plotly.com/python/)
