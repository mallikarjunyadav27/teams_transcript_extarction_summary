import streamlit as st
from langchain_community.utilities.sql_database import SQLDatabase
from langchain_core.prompts.chat import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.runnables import RunnablePassthrough
from langchain_core.runnables.history import RunnableWithMessageHistory
from langchain_core.output_parsers import StrOutputParser
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.chat_history import BaseChatMessageHistory
import psycopg2
from llm import *


tables = ["Billionaires2023"]
host = st.secrets.get("DB_HOST")
database = st.secrets.get("DB_NAME")
username = st.secrets.get("DB_USERNAME")
password = st.secrets.get("DB_PASSWORD")

uri = f"postgresql+psycopg2://{username}:{password}@{host}/{database}"

sqldb = SQLDatabase.from_uri(uri)

# Create persistent chat history storage
chat_history = BaseChatMessageHistory()

# tag::write_message[]
def write_message(role, content):
    """
    This is a helper function that writes a message to the UI
    """

    # Write to UI
    with st.chat_message(role):
        st.markdown(content)
# end::write_message[]


# tag::generate_response[]
def generate_response(user_question):
    # Chat history is automatically handled within final_chain
    standardised_question = final_chain.invoke({"question": user_question})
    
     

    ############## Standardize user question #######################
    # TODO: Implement memory to get the standardised question
    # HINT: https://python.langchain.com/docs/use_cases/question_answering/chat_history#contextualizing-the-question
    
    # Get the standardised_question from user_question and chat history

    #End of TODO
    ################################################################
   
    # This chain reformulates questions based on chat history if needed
    contextualize_q_chain = (
    ChatPromptTemplate.from_template(
        """Given the chat history and the latest user question, reformulate the question \
        to be standalone and understandable without the chat history. Do NOT answer the question, \
        just reformulate it if needed and otherwise return it as is."""
    )
    | MessagesPlaceholder(variable_name="chat_history")  # Placeholder for chat history
    | HumanMessage(content="{question}")  # User's question
    | llm  # Use the language model to process and reformulate
    | StrOutputParser() )

    sqlquery = contextualize_q_chain.invoke({"question": standardised_question})

    # This chain handles the overall question-answering process
    qa_prompt = ChatPromptTemplate.from_template(
    """Based on the table schema below, question, sql query, and sql response, write a natural language response:
    {schema}

    ... (rest of the prompt template)

    {chat_history}  # Placeholder for chat history
    Question: {question}
    SQL Query: {query}
    SQL Response: {response} """)



    final_chain = (
    RunnableWithMessageHistory(  # Wrap the chain with chat history management
        chat_history=chat_history,
        chain=(
            RunnablePassthrough.assign(
                schema=get_schema,
                response=lambda x: run_query(x["query"]),
                question=lambda x: contextualize_q_chain.invoke(x) if x.get("chat_history") else x["question"],  # Conditionally use contextualize_q_chain
            )
            | qa_prompt
            | llm
            | StrOutputParser()
        ),
    )
)

    response = "I am unable to answer your question at this time."
    if (str(sqlquery.upper()).startswith("SELECT")):
        response = final_chain.invoke({"question": standardised_question, "query": sqlquery})

    store_questions(user_question, standardised_question, sqlquery, response)

    return response

# end::generate_response[]


# tag::get_schema[]
def get_schema(_):
    return sqldb.get_table_info()

# end::get_schema[]


# tag::run_query[]
def run_query(query):
    return sqldb.run(query)

# end::run_query[]

# tag::store_questions[]
def store_questions(user_question, 
                    standardised_question, 
                    sqlquery, 
                    response):
 
    conn = psycopg2.connect(host=host, database=database, user=username, password=password)
    conn.autocommit = True
    cursor = conn.cursor()
    query = """INSERT INTO user_questions VALUES (%s, %s, %s, %s)"""
    values = (user_question, standardised_question, sqlquery, response)
    cursor.execute(query, values)
    conn.commit()

    conn.close()
