import streamlit as st
import requests
from bs4 import BeautifulSoup
import pandas as pd
import re
import matplotlib.pyplot as plt
from dotenv import load_dotenv
from google import genai
from google.genai.types import GenerateContentConfig

# SCRAPER CLASS
class WebScraper:
    def __init__(self, inputFile):
        self.inputFile = inputFile
        self.fetchedData = []

    def readUrl(self):
        try:
            df = pd.read_excel(self.inputFile)

            for indx, url in enumerate(df["book_urls"]):
                record = {
                    "productID": indx,
                    "URL": url,
                    "Title": None,
                    "Price": None,
                    "Description": None,
                    "Product Type": None,
                    "Stock": None,
                    "Number of reviews": None
                }
                try:
                    fetched = self.fetchContent(url)
                    record.update(fetched)
                except Exception:
                    pass  # Keep blanks if error
                cleanedRecord = self.preprocessRecords(record)
                self.fetchedData.append(cleanedRecord)

        except Exception:
            return []
        return self.fetchedData

    def fetchContent(self, url=None):
        records = {}
        if url:
            response = requests.get(url=url, timeout=5)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, "html.parser")

            records["Title"] = soup.find("h1").text if soup.find("h1") else None
            records["Price"] = soup.find("p", class_="price_color").text if soup.find("p", class_="price_color") else None
            descTag = soup.find("div", id="product_description")
            records["Description"] = descTag.find_next_sibling("p").text if descTag else None

            rows = soup.find_all('tr')
            for row in rows:
                key = row.find('th').text.strip()
                value = row.find('td').text.strip()
                if key == "Product Type":
                    records["Product Type"] = value
                if key == "Availability":
                    records["Stock"] = value
                if key == "Number of reviews":
                    records["Number of reviews"] = value
        return records

    def preprocessRecords(self, data):
        try:
            # preprocessing the stock value
            if data.get("Stock"):
                match = re.search(r'\((\d+)\savailable\)', data["Stock"])
                if match:
                    data["Stock"] = int(match.group(1))

            # preprocessing the price value - converting from GBR to INR
            if data.get("Price"):
                priceInGbr = data["Price"].replace("Â", "").replace("£","").strip()  # remove weird character
                data["Price"] = priceInGbr

        except Exception as e:
            print(e)
            pass
        return data

    def generateReport(self):
        try:
            df = pd.DataFrame(self.fetchedData)
            total = len(df)
            complete = df.dropna().shape[0]
            incomplete = total - complete
            return {"Total Records": total, "Complete Records": complete, "Incomplete Records": incomplete}
        except Exception:
            return {}

    def askGemini(self, apiKey, productId, question):
        if not apiKey:
            return None

        df = pd.DataFrame(self.fetchedData)
        try:
            row = df[df["productID"] == productId]
            if row.empty:
                return None

            context = row.to_dict(orient="records")[0]
            clients = genai.Client(api_key=apiKey)
            response = clients.models.generate_content(
                model="gemini-2.0-flash",
                contents=f"Here is product information: {context}\n\nQuestion: {question}\n\nAnswer:",
                config=GenerateContentConfig(
                    max_output_tokens=300,
                    temperature=0.7,
                    top_p=0.9
                )
            )
            return response.text
        except Exception:
            return None


# STREAMLIT APP
def main():
    st.title("📘 Product Scraper & Analyzer")

    uploadedFile = st.file_uploader("Upload Excel file with URLs", type=["xlsx"])
    userApiKey = st.sidebar.text_input("🔑 Enter Google API Key", type="password")
    activeApiKey = userApiKey if userApiKey else ""

    if uploadedFile:
        scraper = WebScraper(uploadedFile)
        data = scraper.readUrl()

        if data:
            df = pd.DataFrame(data)
            expectedCols = ["productID", "Title", "Price", "Description",
                            "Product Type", "Stock", "Number of reviews"]
            df = df[expectedCols]

            # Scraped Data
            st.subheader("📑 Scraped Data")
            st.dataframe(df, use_container_width=True)

            st.markdown("---")  # horizontal line

            # Report
            report = scraper.generateReport()
            if report:
                st.subheader("📊 Report Summary")
                col1, col2, col3 = st.columns(3)
                col1.metric(label="Total Records", value=report["Total Records"])
                col2.metric(label="Complete Records", value=report["Complete Records"])
                col3.metric(label="Incomplete Records", value=report["Incomplete Records"])

                col1, col2 = st.columns(2)
                with col1:
                    fig, ax = plt.subplots(figsize=(5, 4))  # fix size
                    ax.bar(["Complete", "Incomplete"],
                           [report["Complete Records"], report["Incomplete Records"]],
                           color=["green", "red"])
                    ax.set_title("Scraping Completion Status")
                    st.pyplot(fig)

                with col2:
                    fig2, ax2 = plt.subplots(figsize=(5, 3.2))  # fix size
                    ax2.pie([report["Complete Records"], report["Incomplete Records"]],
                            labels=["Complete", "Incomplete"],
                            autopct="%1.1f%%",
                            colors=["green", "red"])
                    ax2.set_title("Completion Distribution")
                    st.pyplot(fig2)

            st.markdown("---")  # horizontal line

            # Gemini Section
            st.sidebar.subheader("✨ Ask Gemini About a Product")
            if activeApiKey:
                productId = st.sidebar.number_input("Product ID", min_value=0, max_value=len(df)-1, value=0)
                question = st.sidebar.text_area("Your Question")
                if st.sidebar.button("Ask Gemini"):
                    answer = scraper.askGemini(activeApiKey, productId, question)
                    if answer:
                        st.sidebar.success(f"Gemini's Answer:\n\n{answer}")
                    else:
                        st.sidebar.warning("Could not fetch answer.")
            else:
                st.sidebar.info("Enter API Key to use Gemini.")


if __name__ == "__main__":
    main()
