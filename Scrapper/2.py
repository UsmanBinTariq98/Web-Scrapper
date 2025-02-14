import fitz
from google import genai
import os
import json
import re

client = genai.Client(api_key="AIzaSyCoTc6X7UoErQwCfIAaggza-alK597PUyU")
client_classification = genai.Client(api_key="AIzaSyD-tbV6D3q66YYL_ntE7qIOfbzk_h8zRLM")


def extract_text_from_first_page(pdf_path):
    doc = fitz.open(pdf_path)
    first_page = doc.load_page(0)
    text = first_page.get_text()
    doc.close()
    return text

def extract_title_and_abstract(text):
    lines = text.split('\n')
    title = lines[0]
    abstract = ""
    for line in lines:
        if line.lower().startswith("abstract"):
            abstract = line
            break
    return title, abstract

def categorize_papers(titles_and_abstracts):
    contents = "\n".join([f"Title: {title}\nAbstract: {abstract}" for title, abstract in titles_and_abstracts])
    response = client.models.generate_content(
        model="gemini-2.0-flash",
        contents=f"Identify five common research categories from the following titles and abstracts.:\n{contents}. don't give me any additional expalnation I just need 5 words(e.g Deep Learning, Computer Vision, Reinforcement Learning, NLP, Optimization, etc.)",
    )
    categories = response.text.split('\n')
    # Clean up categories and remove any empty strings
    categories = [category.split('. ')[-1].strip() for category in categories if category.strip()]
    return categories

def classify_papers(titles_and_abstracts, categories):
    contents = "\n".join([f"{i+1}. Title: {title}\n   Abstract: {abstract}" 
                          for i, (title, abstract) in enumerate(titles_and_abstracts)])
    
    response = client_classification.models.generate_content(
        model="gemini-2.0-flash",
        contents=f"""You are a classification model. Categorize each research paper into at least one of these predefined categories: {', '.join(categories)}.
        
        Below are the research paper titles and abstracts:
        {contents}
        
        **STRICTLY return results in this format**:
        1. [Category1, Category2]
        2. [Category3]
        3. [Category1, Category4, Category5]
        ...
        
        DO NOT include any explanations, missing numbers, or blank lines. Ensure that every paper gets a category.
        """
    )

    response_text = response.text.strip()
    print("LLM Response:\n", response_text)  # Debugging step to check output

    # Extract categories using regex
    category_lines = re.findall(r"\d+\.\s\[(.+?)\]", response_text)

    # Ensure proper splitting
    classified_categories = [line.split(", ") for line in category_lines]

    print(f"Expected: {len(titles_and_abstracts)}, Received: {len(classified_categories)}")  # Debugging

    # If mismatch, add "Uncategorized" for missing papers
    while len(classified_categories) < len(titles_and_abstracts):
        classified_categories.append(["Uncategorized"])

    return classified_categories

def update_paper_categories(year, titles_and_abstracts, categories):
    classified_categories = classify_papers(titles_and_abstracts, categories)

    with open(f'pdf_links_{year}.json', 'r', encoding='utf-8') as file:
        papers = json.load(file)

    print(f"Total papers: {len(papers)}, Total classified categories: {len(classified_categories)}")  # Debugging

    if len(papers) == len(classified_categories):
        for paper, category_list in zip(papers, classified_categories):
            paper['categories'] = category_list
    else:
        print("⚠️ Warning: Mismatch detected! Some papers might be missing categories.")

    with open(f'pdf_links_{year}_updated.json', 'w', encoding='utf-8') as file:
        json.dump(papers, file, ensure_ascii=False, indent=4)

def main():
    year = 2021
    pdf_folder = f'pdf_{year}'
    titles_and_abstracts = []

    for pdf_file in os.listdir(pdf_folder):
        if pdf_file.endswith('.pdf'):
            pdf_path = os.path.join(pdf_folder, pdf_file)
            text = extract_text_from_first_page(pdf_path)
            title, abstract = extract_title_and_abstract(text)
            titles_and_abstracts.append((title, abstract))

    categories = categorize_papers(titles_and_abstracts)
    print("Identified Categories:", categories)
    
    update_paper_categories(year, titles_and_abstracts, categories)

if __name__ == '__main__':
    main()