import streamlit as st
## 토큰 개수를 세기위한 라이브러리
import tiktoken
## stream에서 행한 행동이 로그로 남게 하기 위한 라이브러리
from loguru import logger

## 메모리를 가진 체인이 필요
from langchain.chains import ConversationalRetrievalChain
## llm은 gemini꺼
# from langchain.chat_models import Chatgemini
from langchain_google_genai import ChatGoogleGenerativeAI

## 여러 유형의 문서를 이해하기위한 라이브러리(PDF, DOC, PPT)
from langchain.document_loaders import PyPDFLoader
from langchain.document_loaders import Docx2txtLoader
from langchain.document_loaders import UnstructuredPowerPointLoader

## 텍스트 splitter
from langchain.text_splitter import RecursiveCharacterTextSplitter
## 허깅페이스를 사용한 임베딩
from langchain.embeddings import HuggingFaceEmbeddings

## 몇개까지의 대화를 메모리를 넣어줄지 정하기
from langchain.memory import ConversationBufferWindowMemory
## 벡터로 저장하기 위한 라이브러리
# from langchain.vectorstores import FAISS
from langchain.vectorstores import Chroma

# from streamlit_chat import message
from langchain.callbacks import get_openai_callback
from langchain.memory import StreamlitChatMessageHistory


from langchain.prompts import ChatPromptTemplate
from langchain.schema.runnable import RunnableMap

# 메인 함수
def main():
    st.set_page_config(
        page_title="Gemini RAG",
        page_icon=":books:"
    )

    st.title("_Private Data :red[QA Chat]_ :books:")

    ## session_state를 쓰기 위해서 정의하는 함수
    if "conversation" not in st.session_state:
        st.session_state.conversation = None

    if "chat_history" not in st.session_state:
        st.session_state.chat_history = None

    with st.sidebar:
        uploaded_files = st.file_uploader("UPload your file", type=["pdf", 'docx', 'pptx'], accept_multiple_files=True)
        gemini_api_key = st.text_input("GEMINI API Key", key="chatbot_api_key", type="password")
        process = st.button("Process")

    if process:
        if not gemini_api_key:
            st.info("Please add your gemini API key to continue.")
            st.stop()
        files_text = get_text(uploaded_files)
        text_chunks = get_text_chunks(files_text)
        vectorestore = get_vectorstore(text_chunks)

        st.session_state.conversation = get_conversation_chain(vectorestore, gemini_api_key)

        # st.session_state.conversation = get_conversation_chain(vectorestore, gemini_api_key)
        # st.write(st.session_state.conversation)

        st.session_state.processComplete = True

    if 'messages' not in st.session_state:
        st.session_state['messages'] = [{'role' : 'assistant',
                                         "content" : "안녕하세요! 주어진 문서에 대해 궁금하신 것이 있으면 언제든 물어봐주세요!"}]
        
    for message in st.session_state.messages:
        ## 메시지마다 어떤 아이콘을 넣을지
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    history = StreamlitChatMessageHistory(key="chat_messages")

    # Chat logic
    if query := st.chat_input("질문을 입력해주세요."):
        print(query)
        st.session_state.messages.append({"role": "user",
                                          "content" : query})
        
        with st.chat_message("user"):
            st.markdown(query)

        with st.chat_message("assistant"):

            chain = st.session_state.conversation
            # chain = get_conversation_chain(vectorestore, gemini_api_key)

            with st.spinner("Thinking..."):
                result = chain.invoke({'question':query})
                # # with get_openai_callback() as cb:
                # st.session_state.chat_history = result.chat_history
                # response = result.content
                # source_documents = result.source_documents
                # st.session_state.chat_history = result.chat_history
                response = result.content
                # source_documents = result.source_documents

                st.markdown(response)
                source_documents = get_source(vectorestore, query)
                with st.expander("참고 문서 확인"):
                    st.markdown(f"출처: {source_documents[0].metadata['source']}의 {source_documents[0].metadata['page']} 페이지", help=source_documents[0].page_content)          # help를 붙이면 ?아이콘 생김 -> 마우스 대면 원하는 글이 뜸
                    st.markdown(f"출처: {source_documents[0].metadata['source']}의 {source_documents[0].metadata['page']} 페이지", help=source_documents[1].page_content)
                    st.markdown(f"출처: {source_documents[0].metadata['source']}의 {source_documents[0].metadata['page']} 페이지", help=source_documents[2].page_content)
                
        st.session_state.messages.append({'role': "assistant",
                                          "content": response})
        



# 유틸리티 함수
        
def tiktoken_len(text):
    tokenizer = tiktoken.get_encoding("cl100k_base")
    tokens = tokenizer.encode(text)

    return len(tokens)

def get_text(docs):

    doc_list = []

    for doc in docs:
        ## streamlit 서버 상에 파일이 업로드되면서 경로가 바뀌기에 서버상 경로로 설정
        file_name = doc.name
        with open(file_name, "wb") as file:
            file.write(doc.getvalue())
            logger.info(f"Uploaded {file_name}")

        if '.pdf' in doc.name:
            loader = PyPDFLoader(file_name)
            documents = loader.load_and_split()

        elif '.docx' in doc.name:
            loader = Docx2txtLoader(file_name)
            documents = loader.load_and_split()

        elif '.pptx' in doc.name:
            loader = UnstructuredPowerPointLoader(file_name)
            documents = loader.load_and_split()

        doc_list.extend(documents)

    return doc_list

def get_text_chunks(text):
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size = 1000,
        chunk_overlap=100,
        length_function=tiktoken_len
    )
    chunks = text_splitter.split_documents(text)
    return chunks

def get_vectorstore(text_chunks):

    model_name = "jhgan/ko-sroberta-multitask"
    model_kwargs = {'device': 'cpu'}
    encode_kwargs = {'normalize_embeddings': True}
    hf = HuggingFaceEmbeddings(
        model_name=model_name,
        model_kwargs=model_kwargs,
        encode_kwargs=encode_kwargs
    )

    # vectordb = FAISS.from_documents(text_chunks, embeddings)
    docsearch = Chroma.from_documents(text_chunks, hf)

    return docsearch

def get_source(docsearch, query):

    retriever=docsearch.as_retriever(
                                    search_type="mmr",
                                    search_kwargs={'k':3, 'fetch_k': 10},
                                    # vervose=True
                                    )
    source = retriever.get_relevant_documents(query)

    return docsearch

def get_conversation_chain(docsearch, gemini_api_key):
        
    template = """Answer the question as based only on the following context:
    {context}

    Question: {question}
    """

    gemini = ChatGoogleGenerativeAI(model="gemini-pro", google_api_key=gemini_api_key, temperature = 0)
    # conversation_chain = ConversationalRetrievalChain.from_llm(
    #     llm=gemini,
    #     chain_type="stuff",
    #     condense_question_prompt=ChatPromptTemplate.from_template(template),
    #     retriever=docsearch.as_retriever(
    #                                 search_type="mmr",
    #                                 # search_kwargs={'k':3, 'fetch_k': 10},
    #                                 vervose=True),
    #     memory=ConversationBufferWindowMemory(memory_key='chat_history', return_messages=True, output_key='answer'),      # 'chat history라는 키 값을 가져와 기억함
    #     get_chat_history = lambda h: h,     # 메모리가 들어온 그대로 chat history로 보낸다
    #     return_source_documents = True,
    #     verbose=True
    #     )


    prompt = ChatPromptTemplate.from_template(template)
    retriever=docsearch.as_retriever(
                                    search_type="mmr",
                                    # search_kwargs={'k':3, 'fetch_k': 10},
                                    vervose=True)
    retriever.get_relevant_documents("LGG에 대해서 설명해줘")
    conversation_chain = RunnableMap({
        "context": lambda x: retriever.get_relevant_documents(x['question']),
        "question": lambda x: x['question']
    }) | prompt | gemini

    return conversation_chain

if __name__ == "__main__":
    main()
